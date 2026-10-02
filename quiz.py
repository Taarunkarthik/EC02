"""Server-only rapid-fire quiz. Never shares answer keys with participant clients."""
from datetime import datetime, timedelta, timezone
from database import get_db_connection

QUIZ_MINUTES = 10
QUESTION_SECONDS = 60
# Kept out of static assets and participant HTML/JSON.
QUESTIONS = [
    ("R01", "Which data structure follows last in, first out (LIFO)?", ["Queue", "Stack", "Graph", "Heap"], 1),
    ("R02", "What is the decimal value of binary 1010?", ["8", "9", "10", "12"], 2),
    ("R03", "Which Git command creates a new branch and switches to it?", ["git status", "git switch -c feature", "git fetch feature", "git merge feature"], 1),
    ("R04", "What does an HTTP 404 response mean?", ["Request succeeded", "Server is restarting", "Resource not found", "Authentication succeeded"], 2),
    ("R05", "What is the worst-case time complexity of binary search on a sorted array?", ["O(1)", "O(log n)", "O(n)", "O(n²)"], 1),
    ("R06", "In Python, what does len([0, 1, 2, 3]) return?", ["3", "4", "5", "An error"], 1),
    ("R07", "Which condition stops a recursive function from calling itself forever?", ["A base case", "A global variable", "A compiler flag", "A print statement"], 0),
    ("R08", "Which SQL clause filters rows before grouping?", ["ORDER BY", "HAVING", "WHERE", "LIMIT"], 2),
    ("R09", "What is the result of the Boolean expression true AND false?", ["true", "false", "null", "undefined"], 1),
    ("R10", "In conventional command-line programs, exit status 0 usually indicates…", ["An infinite loop", "A syntax error", "Successful completion", "An unavailable file"], 2),
]


def _now():
    return datetime.now(timezone.utc)


def _parse(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _advance_expired(cur, team_id, session, now, closed=False):
    """Persist timeout transitions so a refresh cannot reset a question clock."""
    if session is None or session["completed_at"]:
        return
    count = cur.execute("SELECT COUNT(*) FROM quiz_answers WHERE team_id = ?", (team_id,)).fetchone()[0]
    question_start = _parse(session["question_started_at"])
    ended = now >= _parse(session["ends_at"]) or closed
    while count < len(QUESTIONS) and (ended or now >= question_start + timedelta(seconds=QUESTION_SECONDS)):
        cur.execute("INSERT OR IGNORE INTO quiz_answers (team_id, question_id, answer_index, points) VALUES (?, ?, NULL, 0)",
                    (team_id, QUESTIONS[count][0]))
        count += 1
        question_start += timedelta(seconds=QUESTION_SECONDS)
    cur.execute("UPDATE quiz_sessions SET question_started_at = ? WHERE team_id = ?", (question_start.isoformat(), team_id))
    if count == len(QUESTIONS):
        cur.execute("UPDATE quiz_sessions SET completed_at = ? WHERE team_id = ?", (now.isoformat(), team_id))


def _snapshot(cur, team_id, now):
    controls = cur.execute("SELECT quiz_status FROM competition_controls WHERE id = 1").fetchone()
    status = controls["quiz_status"]
    session = cur.execute("SELECT * FROM quiz_sessions WHERE team_id = ?", (team_id,)).fetchone()
    _advance_expired(cur, team_id, session, now, status == "CLOSED")
    session = cur.execute("SELECT * FROM quiz_sessions WHERE team_id = ?", (team_id,)).fetchone()
    answers = cur.execute("SELECT COUNT(*) AS count, COALESCE(SUM(points), 0) AS score FROM quiz_answers WHERE team_id = ?", (team_id,)).fetchone()
    count, score = answers["count"], answers["score"]
    completed = bool(session and session["completed_at"])
    question = None
    remaining = question_remaining = 0
    if session and not completed and status == "OPEN":
        qid, prompt, choices, _ = QUESTIONS[count]
        question = {"id": qid, "prompt": prompt, "options": choices, "number": count + 1}
        remaining = max(0, int((_parse(session["ends_at"]) - now).total_seconds()))
        question_remaining = max(0, min(remaining, int((_parse(session["question_started_at"]) + timedelta(seconds=QUESTION_SECONDS) - now).total_seconds())))
    return {"status": status, "started": session is not None, "completed": completed,
            "quiz_score": score, "quiz_total": len(QUESTIONS), "answered_count": count,
            "remaining_seconds": remaining, "question_remaining_seconds": question_remaining,
            "current_question": question}


def quiz_snapshot(team_id):
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        snapshot = _snapshot(conn.cursor(), team_id, _now())
        conn.commit()
        return snapshot
    finally:
        conn.close()


def start_quiz(team_id):
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        if cur.execute("SELECT event_status FROM event_state WHERE id = 1").fetchone()[0] != "COMPLETED":
            return None, "The quiz opens after debugging is complete."
        if cur.execute("SELECT quiz_status FROM competition_controls WHERE id = 1").fetchone()[0] != "OPEN":
            return None, "The organizers have not opened the quiz."
        now = _now()
        cur.execute("INSERT OR IGNORE INTO quiz_sessions (team_id, started_at, ends_at, question_started_at) VALUES (?, ?, ?, ?)",
                    (team_id, now.isoformat(), (now + timedelta(minutes=QUIZ_MINUTES)).isoformat(), now.isoformat()))
        snapshot = _snapshot(cur, team_id, now)
        conn.commit()
        return snapshot, None
    finally:
        conn.close()


def answer_quiz(team_id, question_id, answer_index):
    if not isinstance(question_id, str) or type(answer_index) is not int or not 0 <= answer_index < 4:
        return None, "Select one answer before locking it."
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.cursor()
        now = _now()
        snapshot = _snapshot(cur, team_id, now)
        # Retry is harmless, including a lost response followed by a refresh.
        if cur.execute("SELECT 1 FROM quiz_answers WHERE team_id = ? AND question_id = ?", (team_id, question_id)).fetchone():
            conn.commit()
            return snapshot, None
        question = snapshot["current_question"]
        if snapshot["status"] != "OPEN" or question is None:
            conn.commit()
            return None, "The quiz is not accepting answers."
        if question["id"] != question_id:
            conn.commit()
            return None, "This question is no longer active. Continue with the current question."
        key = QUESTIONS[question["number"] - 1][3]
        cur.execute("INSERT INTO quiz_answers (team_id, question_id, answer_index, points) VALUES (?, ?, ?, ?)",
                    (team_id, question_id, answer_index, int(answer_index == key)))
        cur.execute("UPDATE quiz_sessions SET question_started_at = ? WHERE team_id = ?", (now.isoformat(), team_id))
        if question["number"] == len(QUESTIONS):
            cur.execute("UPDATE quiz_sessions SET completed_at = ? WHERE team_id = ?", (now.isoformat(), team_id))
        snapshot = _snapshot(cur, team_id, now)
        conn.commit()
        return snapshot, None
    finally:
        conn.close()
