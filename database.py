import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from config import Config

def get_db_connection():
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
    db_path = Config.DATABASE_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = get_db_connection()
    with open(Config.SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    
    if force_reset:
        cur_drop = conn.cursor()
        cur_drop.execute("PRAGMA foreign_keys = OFF;")
        cur_drop.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur_drop.fetchall() if not r[0].startswith("sqlite_")]
        for t in tables:
            cur_drop.execute(f"DROP TABLE IF EXISTS {t}")
        cur_drop.execute("PRAGMA foreign_keys = ON;")
        conn.commit()

    conn.executescript(schema_sql)
    
    # Initialize event_state row if missing
    cur = conn.cursor()
    cur.execute("SELECT id FROM event_state WHERE id = 1")
    if not cur.fetchone():
        cfg = Config.load_event_config()
        dur = cfg.get("duration_minutes", 70)
        cur.execute("""
            INSERT INTO event_state (id, event_status, duration_minutes, remaining_seconds, is_paused)
            VALUES (1, 'WAITING', ?, ?, 0)
        """, (dur, dur * 60))
    
    # Seed Questions from data/questions.json
    cur.execute("SELECT COUNT(*) as count FROM questions")
    if cur.fetchone()["count"] == 0 or force_reset:
        if os.path.exists(Config.QUESTIONS_JSON_PATH):
            with open(Config.QUESTIONS_JSON_PATH, "r", encoding="utf-8") as f:
                questions = json.load(f)
            for q in questions:
                cur.execute("""
                    INSERT OR REPLACE INTO questions 
                    (id, language, title, difficulty, code, error_type, bug_location, expected_output, cause, correction, points, hint, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    q["id"], q["language"], q["title"], q.get("difficulty", "Medium"),
                    q["code"], q["error_type"], q["bug_location"], q["expected_output"],
                    q["cause"], q["correction"], q.get("points", q.get("base_points", 20)),
                    q.get("hint", "")
                ))
                
    conn.commit()
    conn.close()

def generate_team_id(conn):
    cur = conn.cursor()
    cur.execute("SELECT id FROM teams ORDER BY id DESC")
    rows = cur.fetchall()
    max_num = 0
    for r in rows:
        tid = r["id"]
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
    """
    Registers a new team of 2–3 members.
    Enforces non-empty team name and 2-3 members.
    Prevents duplicate team names.
    """
    name = (team_name or "").strip()
    m1 = (member1 or "").strip()
    m2 = (member2 or "").strip()
    m3 = (member3 or "").strip() if member3 else ""
    em = (email or "").strip() if email else ""

    if not name:
        return None, "Team name is required."
    if not m1 or not m2:
        return None, "A team must have at least 2 members (Member 1 and Member 2 are required)."

    # Count valid members
    members = [m1, m2]
    if m3:
        members.append(m3)

    if len(members) < 2 or len(members) > 3:
        return None, "Team size must be strictly between 2 and 3 members."

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check duplicate name
        cur.execute("SELECT id FROM teams WHERE UPPER(name) = UPPER(?)", (name,))
        if cur.fetchone():
            return None, f"Team name '{name}' is already registered. Please choose a unique name."

        team_id = generate_team_id(conn)
        cur.execute("INSERT INTO teams (id, name) VALUES (?, ?)", (team_id, name))

        # Insert participants
        cur.execute("INSERT INTO participants (team_id, name, role, email) VALUES (?, ?, 'Lead', ?)", (team_id, m1, em))
        cur.execute("INSERT INTO participants (team_id, name, role, email) VALUES (?, ?, 'Member 2', ?)", (team_id, m2, em))
        if m3:
            cur.execute("INSERT INTO participants (team_id, name, role, email) VALUES (?, ?, 'Member 3', ?)", (team_id, m3, em))

        # Initialize score row
        cur.execute("""
            INSERT INTO scores (team_id, score, bonus_score, completed_count)
            VALUES (?, 0, 0, 0)
        """, (team_id,))

        # Initialize power-ups (1 each per team)
        for pu in ["RUBBER_DUCK", "GIT_REVERT", "DOUBLE_COMMIT"]:
            cur.execute("INSERT INTO powerups (team_id, powerup_type, is_used) VALUES (?, ?, 0)", (team_id, pu))

        # Assign initial progressive questions
        assign_initial_questions(team_id, cur)

        conn.commit()
        return team_id, None
    except sqlite3.IntegrityError as e:
        conn.rollback()
        return None, f"Registration error: {str(e)}"
    finally:
        conn.close()

def assign_initial_questions(team_id, cur=None):
    """
    Assigns questions sequentially for the team.
    Q01 is unlocked immediately, subsequent questions unlock progressively upon submission.
    """
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

def get_team_assigned_questions(team_id):
    """Returns list of assigned questions with progression status for the team."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT q.id, q.language, q.title, q.difficulty, q.points,
               qa.question_order, qa.is_unlocked, qa.is_completed, qa.is_abandoned
        FROM question_assignments qa
        JOIN questions q ON qa.question_id = q.id
        WHERE qa.team_id = ? AND qa.is_abandoned = 0
        ORDER BY qa.question_order ASC
    """, (team_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_client_question(team_id, question_id):
    """
    Returns sanitized question data for the client.
    Never exposes bug location, error type, expected output, cause, or correction!
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT q.id, q.language, q.title, q.difficulty, q.points, q.code,
               qa.question_order, qa.is_unlocked, qa.is_completed
        FROM question_assignments qa
        JOIN questions q ON qa.question_id = q.id
        WHERE qa.team_id = ? AND qa.question_id = ? AND qa.is_abandoned = 0
    """, (team_id, question_id))
    q = cur.fetchone()
    conn.close()
    return dict(q) if q else None

def unlock_next_question(team_id, current_order, cur=None):
    """Unlocks the next sequential question for the team."""
    close_conn = False
    if cur is None:
        conn = get_db_connection()
        cur = conn.cursor()
        close_conn = True

    try:
        cur.execute("""
            UPDATE question_assignments 
            SET is_unlocked = 1 
            WHERE team_id = ? AND question_order = ?
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
