import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from config import Config
from answer_feedback import answer_field_results


def normalize_database_url(raw_url):
    if not raw_url:
        return raw_url
    value = raw_url.strip()
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    return value


def prepare_compat_sql(sql):
    sql_text = (sql or "").strip()
    if not sql_text:
        return sql_text

    upper_sql = sql_text.upper()
    if "PRAGMA TABLE_INFO(" in upper_sql:
        table_name = re.search(r"PRAGMA\s+TABLE_INFO\s*\(\s*([A-Za-z0-9_]+)\s*\)", sql_text, re.I)
        if table_name:
            table = table_name.group(1)
            return (
                f"SELECT column_name AS name FROM information_schema.columns "
                f"WHERE table_schema = 'public' AND table_name = '{table}' "
                "ORDER BY ordinal_position"
            )

    if upper_sql.startswith("PRAGMA "):
        return "SELECT 1"
    if upper_sql.startswith("BEGIN IMMEDIATE"):
        return "BEGIN"

    sql_text = re.sub(
        r"GROUP_CONCAT\s*\(\s*([^,()]+?)\s*,\s*([^()]+?)\s*\)",
        r"STRING_AGG(\1, \2)",
        sql_text,
        flags=re.I,
    )
    sql_text = re.sub(
        r"datetime\(\s*'now'\s*,\s*'(-\d+\s+(?:second|seconds|minute|minutes))'\s*\)",
        r"CURRENT_TIMESTAMP - INTERVAL '\1'",
        sql_text,
        flags=re.I,
    )
    sql_text = sql_text.replace("MIN(violations + 1, ?)", "LEAST(violations + 1, ?)")

    if upper_sql.startswith("INSERT OR IGNORE"):
        sql_text = re.sub(r"(?is)^INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql_text)
        sql_text = sql_text.rstrip(";")
        if " ON CONFLICT" not in sql_text.upper():
            sql_text = f"{sql_text} ON CONFLICT DO NOTHING"
        return sql_text.replace("?", "%s")

    if "INSERT OR IGNORE" in upper_sql:
        sql_text = re.sub(r"(?is)INSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql_text)
        sql_text = sql_text.rstrip(";")
        if " ON CONFLICT" not in sql_text.upper():
            sql_text = f"{sql_text} ON CONFLICT DO NOTHING"

    return sql_text.replace("?", "%s")


def iter_sql_statements(sql_text):
    buffer = []
    for raw_line in (sql_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        buffer.append(raw_line)
        candidate = "\n".join(buffer).strip()
        if sqlite3.complete_statement(candidate):
            if candidate:
                yield candidate
            buffer = []
    if buffer:
        candidate = "\n".join(buffer).strip()
        if candidate:
            yield candidate


class CompatRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class CompatCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        normalized_sql = prepare_compat_sql(sql)
        if params is None:
            self._cursor.execute(normalized_sql)
        else:
            self._cursor.execute(normalized_sql, params)
        return self

    def executemany(self, sql, params_seq):
        normalized_sql = prepare_compat_sql(sql)
        self._cursor.executemany(normalized_sql, params_seq)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return CompatRow(row)
        columns = [col[0] for col in self._cursor.description]
        return CompatRow(dict(zip(columns, row)))

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return [CompatRow(row) for row in rows]
        columns = [col[0] for col in self._cursor.description]
        return [CompatRow(dict(zip(columns, row))) for row in rows]

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class CompatConnection:
    def __init__(self, connection):
        self._conn = connection

    def cursor(self):
        return CompatCursor(self._conn.cursor(cursor_factory=RealDictCursor))

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def executescript(self, sql):
        statements = list(iter_sql_statements(sql))
        cursor = self._conn.cursor()
        for statement in statements:
            cursor.execute(prepare_compat_sql(statement))
        self._conn.commit()


def get_db_connection():
    database_url = Config.DATABASE_URL or os.environ.get("SUPABASE_DATABASE_URL")
    if database_url:
        normalized_url = normalize_database_url(database_url)
        conn = psycopg2.connect(
            normalized_url,
            connect_timeout=10,
            sslmode="require",
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5,
        )
        conn.autocommit = False
        return CompatConnection(conn)

    db_path = Config.DATABASE_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
    except Exception:
        pass
    return conn


def init_db(force_reset=False):
    conn = get_db_connection()
    with open(Config.SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    if force_reset:
        cur_drop = conn.cursor()
        if isinstance(conn, CompatConnection):
            cur_drop.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name NOT LIKE 'pg_%' ORDER BY table_name")
            tables = [row["table_name"] for row in cur_drop.fetchall() if row["table_name"] not in {"spatial_ref_sys"}]
            for table_name in tables:
                cur_drop.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
        else:
            cur_drop.execute("PRAGMA foreign_keys = OFF;")
            cur_drop.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cur_drop.fetchall() if not row[0].startswith("sqlite_")]
            for table_name in tables:
                cur_drop.execute(f"DROP TABLE IF EXISTS {table_name}")
            cur_drop.execute("PRAGMA foreign_keys = ON;")
        conn.commit()

    if isinstance(conn, CompatConnection):
        conn.executescript(schema_sql)
    else:
        conn.executescript(schema_sql)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(submissions)")}
    for name in ("request_id", "response_json"):
        if name not in columns:
            conn.execute(f"ALTER TABLE submissions ADD COLUMN {name} TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_submission_request ON submissions(team_id, request_id) WHERE request_id IS NOT NULL")
    session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(fullscreen_sessions)")}
    for name in ("active_event_id", "document_id"):
        if name not in session_columns:
            conn.execute(f"ALTER TABLE fullscreen_sessions ADD COLUMN {name} TEXT")
    if "document_started_at" not in session_columns:
        conn.execute("ALTER TABLE fullscreen_sessions ADD COLUMN document_started_at REAL NOT NULL DEFAULT 0")
    conn.execute("INSERT OR IGNORE INTO competition_controls (id, generation) VALUES (1, ?)", (uuid.uuid4().hex,))

    conn.execute("""INSERT INTO team_activity (team_id, event_type, created_at)
        SELECT old.team_id,
               CASE old.event_type WHEN 'focus_lost' THEN 'window_blur'
                 WHEN 'focus_regained' THEN 'window_focus'
                 WHEN 'tab_visible' THEN 'window_visible' ELSE old.event_type END,
               old.created_at
        FROM activity_events old
        WHERE NOT EXISTS (SELECT 1 FROM team_activity current
          WHERE current.team_id = old.team_id AND current.created_at = old.created_at
          AND current.event_type = CASE old.event_type WHEN 'focus_lost' THEN 'window_blur'
            WHEN 'focus_regained' THEN 'window_focus'
            WHEN 'tab_visible' THEN 'window_visible' ELSE old.event_type END)""")

    cur = conn.cursor()
    cfg = Config.load_event_config()
    dur = cfg.get("duration_minutes", 40)
    cur.execute("SELECT id FROM event_state WHERE id = 1")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO event_state (id, event_status, duration_minutes, remaining_seconds, is_paused)
            VALUES (1, 'WAITING', ?, ?, 0)
        """, (dur, dur * 60))
    cur.execute("""
        UPDATE event_state SET duration_minutes = ?, remaining_seconds = ?
        WHERE id = 1 AND event_status = 'WAITING' AND event_start_time IS NULL
    """, (dur, dur * 60))

    question_columns = {row["name"] for row in conn.execute("PRAGMA table_info(questions)")}
    for name in ("cause_keywords", "correction_keywords"):
        if name not in question_columns:
            conn.execute(f"ALTER TABLE questions ADD COLUMN {name} TEXT")
    bank_version = "c-python-beginner-bank-v1"
    if not conn.execute("SELECT 1 FROM data_migrations WHERE name = ?", (bank_version,)).fetchone():
        with open(Config.QUESTIONS_JSON_PATH, encoding="utf-8") as f:
            questions = json.load(f)
        for q in questions:
            cur.execute("""INSERT INTO questions
                (id, language, title, difficulty, code, error_type, bug_location, expected_output,
                 cause, correction, points, hint, cause_keywords, correction_keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET language=excluded.language, title=excluded.title,
                difficulty=excluded.difficulty, code=excluded.code, error_type=excluded.error_type,
                bug_location=excluded.bug_location, expected_output=excluded.expected_output,
                cause=excluded.cause, correction=excluded.correction, points=excluded.points,
                hint=excluded.hint, cause_keywords=excluded.cause_keywords,
                correction_keywords=excluded.correction_keywords""",
                (q["id"], q["language"], q["title"], q.get("difficulty", "Medium"), q["code"],
                 q["error_type"], q["bug_location"], q["expected_output"], q["cause"], q["correction"],
                 q.get("points", q.get("base_points", 20)), q.get("hint", ""),
                 json.dumps(q.get("cause_keywords", [])), json.dumps(q.get("correction_keywords", []))))
        conn.execute("INSERT INTO data_migrations(name) VALUES (?)", (bank_version,))

    conn.commit()
    conn.close()


def generate_team_id(conn):
    cur = conn.cursor()
    cur.execute("SELECT id FROM teams ORDER BY id DESC")
    rows = cur.fetchall()
    max_num = 0
    for row in rows:
        tid = row["id"]
        if tid.startswith("EX0-"):
            try:
                num = int(tid.split("-")[1])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    next_num = max_num + 1
    return f"EX0-{next_num:03d}"


def register_team(team_name, member1, member2, member3=None, email=None, password=None):
    name = (team_name or "").strip()
    m1 = (member1 or "").strip()
    m2 = (member2 or "").strip()
    m3 = (member3 or "").strip() if member3 else ""
    em = (email or "").strip() if email else ""

    if not name:
        return None, "Team name is required."
    if any(len(value) > 80 for value in (name, m1, m2, m3)) or len(em) > 254:
        return None, "Team and member names must be 80 characters or fewer."
    if not m1 or not m2:
        return None, "A team must have at least 2 members (Member 1 and Member 2 are required)."

    members = [m1, m2]
    if m3:
        members.append(m3)

    if len(members) < 2 or len(members) > 3:
        return None, "Team size must be strictly between 2 and 3 members."

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if cur.execute("SELECT results_published FROM competition_controls WHERE id = 1").fetchone()[0]:
            return None, "Registration is closed because final results have been published."
        cur.execute("SELECT id FROM teams WHERE UPPER(name) = UPPER(?)", (name,))
        if cur.fetchone():
            return None, f"Team name '{name}' is already registered. Please choose a unique name."

        team_id = generate_team_id(conn)
        cur.execute("INSERT INTO teams (id, name) VALUES (?, ?)", (team_id, name))
        cur.execute("INSERT INTO participants (team_id, name, role, email) VALUES (?, ?, 'Lead', ?)", (team_id, m1, em))
        cur.execute("INSERT INTO participants (team_id, name, role, email) VALUES (?, ?, 'Member 2', ?)", (team_id, m2, em))
        if m3:
            cur.execute("INSERT INTO participants (team_id, name, role, email) VALUES (?, ?, 'Member 3', ?)", (team_id, m3, em))
        cur.execute("INSERT INTO scores (team_id, score, bonus_score, completed_count) VALUES (?, 0, 0, 0)", (team_id,))

        for pu in ["RUBBER_DUCK", "GIT_REVERT", "DOUBLE_COMMIT"]:
            cur.execute("INSERT INTO powerups (team_id, powerup_type, is_used) VALUES (?, ?, 0)", (team_id, pu))

        assign_initial_questions(team_id, cur)
        conn.commit()
        return team_id, None
    except (sqlite3.IntegrityError, psycopg2.IntegrityError):
        conn.rollback()
        return None, "Registration could not be saved. Please try a different team name."
    finally:
        conn.close()


def assign_initial_questions(team_id, cur=None):
    close_conn = False
    if cur is None:
        conn = get_db_connection()
        cur = conn.cursor()
        close_conn = True

    try:
        cur.execute("SELECT COUNT(*) as c FROM question_assignments WHERE team_id = ?", (team_id,))
        if cur.fetchone()["c"] > 0:
            return

        cur.execute("SELECT id FROM questions WHERE is_active = 1 ORDER BY id ASC")
        questions = cur.fetchall()

        for order, q in enumerate(questions, 1):
            is_unlocked = 1 if order == 1 else 0
            cur.execute("""
                INSERT OR IGNORE INTO question_assignments
                (team_id, question_id, question_order, is_unlocked, is_completed, is_abandoned)
                VALUES (?, ?, ?, ?, 0, 0)
            """, (team_id, q["id"], order, is_unlocked))

        if close_conn:
            conn.commit()
    finally:
        if close_conn:
            conn.close()


def _answer_summary(conn, team_id, question_id, points, include_submission=False):
    row = conn.execute("SELECT * FROM submissions WHERE team_id = ? AND question_id = ? ORDER BY is_accepted DESC, total_score DESC, id ASC LIMIT 1", (team_id, question_id)).fetchone()
    result = {"is_answered": bool(row), "answer_status": None, "awarded_score": 0, "max_score": points}
    if row:
        evaluation = json.loads(row["response_json"] or "{}")
        raw = sum(row[key] for key in ("error_loc_score", "error_type_score", "cause_score", "output_score", "correction_score"))
        result.update(
            awarded_score=row["total_score"],
            max_score=evaluation.get("max_score", points * (2 if row["is_double_commit"] else 1)),
            answer_status=evaluation.get("answer_status") or ("correct" if raw >= points else "partial" if raw > 0 else "incorrect"),
        )
        if row["override_reason"]:
            result["answer_status"] = "correct" if row["total_score"] >= result["max_score"] else "partial" if row["total_score"] > 0 else "incorrect"
        result["field_results"] = answer_field_results(dict(row), evaluation.get("base_points", points))
        result["score_overridden"] = bool(row["override_reason"])
        result["penalties"] = evaluation.get("penalties", {})
        for key in ("hint_used", "swap_used", "is_double_commit"):
            result[key] = evaluation.get(key, 0)
        if include_submission:
            result["submission"] = {key: row[key] for key in ("error_location", "error_type", "expected_output", "cause", "correction")}
    return result


def get_team_assigned_questions(team_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT q.id, q.difficulty, q.points,
               qa.question_order, qa.is_unlocked, qa.is_completed, qa.is_abandoned
        FROM question_assignments qa
        JOIN questions q ON qa.question_id = q.id
        WHERE qa.team_id = ? AND qa.is_abandoned = 0
        ORDER BY qa.question_order ASC
    """, (team_id,))
    rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row.update(_answer_summary(conn, team_id, row["id"], row["points"]))
    conn.close()
    return rows


def get_client_question(team_id, question_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT q.id, q.language, q.title, q.difficulty, q.points, q.code,
               qa.question_order, qa.is_unlocked, qa.is_completed
        FROM question_assignments qa
        JOIN questions q ON qa.question_id = q.id
        WHERE qa.team_id = ? AND qa.question_id = ? AND qa.is_abandoned = 0 AND qa.is_unlocked = 1
    """, (team_id, question_id))
    q = cur.fetchone()
    result = dict(q) if q else None
    if result:
        result.update(_answer_summary(conn, team_id, question_id, result["points"], include_submission=True))
    conn.close()
    return result


def unlock_next_question(team_id, current_order, cur=None):
    close_conn = False
    if cur is None:
        conn = get_db_connection()
        cur = conn.cursor()
        close_conn = True

    try:
        cur.execute("""
            UPDATE question_assignments
            SET is_unlocked = 1
            WHERE team_id = ? AND question_order = ? AND is_abandoned = 0
        """, (team_id, current_order + 1))
        if close_conn:
            conn.commit()
    finally:
        if close_conn:
            conn.close()


def log_admin_action(action, details=""):
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO admin_actions (action, details) VALUES (?, ?)", (action, details))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def record_activity(team_id, event_type, question_id=None, cur=None):
    owned = cur is None
    conn = get_db_connection() if owned else None
    cur = conn.cursor() if owned else cur
    try:
        cur.execute("INSERT INTO team_activity (team_id, event_type, question_id) VALUES (?, ?, ?)", (team_id, event_type, question_id))
        if owned:
            conn.commit()
    finally:
        if owned:
            conn.close()


def get_competition_controls():
    conn = get_db_connection()
    try:
        return dict(conn.execute("SELECT * FROM competition_controls WHERE id = 1").fetchone())
    finally:
        conn.close()
