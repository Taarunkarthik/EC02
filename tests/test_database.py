import pytest
import sqlite3
from database import init_db, get_db_connection, register_team, generate_team_id, get_team_assigned_questions, get_client_question
from event_manager import reset_event_data

@pytest.fixture(autouse=True)
def setup_clean_db():
    init_db(force_reset=True)
    yield
    reset_event_data("RESET EVENT")

def test_database_initialization():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Verify core 9 tables exist per Section 31
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r["name"] for r in cur.fetchall()}
    required_tables = {
        "teams", "participants", "questions", "question_assignments",
        "submissions", "scores", "powerups", "event_state", "admin_actions"
    }
    assert required_tables.issubset(tables)

    # Check 30 verified debugging questions seeded
    cur.execute("SELECT COUNT(*) as count FROM questions WHERE is_active = 1")
    count = cur.fetchone()["count"]
    assert count == 30

    # Check initial event_state
    cur.execute("SELECT * FROM event_state WHERE id = 1")
    st = cur.fetchone()
    assert st["event_status"] == "WAITING"
    assert st["duration_minutes"] == 40
    assert st["remaining_seconds"] == 2400

    conn.close()

def test_team_registration():
    team_id, err = register_team("ByteForce", "Alice Smith", "Bob Jones", "Charlie Brown", "byteforce@example.com")
    assert err is None
    assert team_id.startswith("EX0-")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
    team = cur.fetchone()
    assert team["name"] == "ByteForce"
    assert team["is_active"] == 1

    # Verify participants (2-3 members)
    cur.execute("SELECT name, role FROM participants WHERE team_id = ? ORDER BY id ASC", (team_id,))
    members = cur.fetchall()
    assert len(members) == 3
    assert members[0]["name"] == "Alice Smith"
    assert members[1]["name"] == "Bob Jones"
    assert members[2]["name"] == "Charlie Brown"

    # Verify score row initialized
    cur.execute("SELECT score, completed_count FROM scores WHERE team_id = ?", (team_id,))
    sc = cur.fetchone()
    assert sc["score"] == 0.0
    assert sc["completed_count"] == 0

    # Verify 3 powerups initialized (Rubber Duck, Git Revert, Double Commit)
    cur.execute("SELECT powerup_type, is_used FROM powerups WHERE team_id = ?", (team_id,))
    pu = {r["powerup_type"]: r["is_used"] for r in cur.fetchall()}
    assert pu["RUBBER_DUCK"] == 0
    assert pu["GIT_REVERT"] == 0
    assert pu["DOUBLE_COMMIT"] == 0

    conn.close()

def test_waiting_round_adopts_new_duration_without_losing_teams():
    team_id, error = register_team("Existing waiting team", "Dev A", "Dev B")
    assert error is None
    conn = get_db_connection()
    conn.execute("UPDATE event_state SET duration_minutes = 70, remaining_seconds = 4200 WHERE id = 1")
    conn.commit()
    conn.close()

    init_db()
    conn = get_db_connection()
    state = conn.execute("SELECT * FROM event_state WHERE id = 1").fetchone()
    assert state["duration_minutes"] == 40 and state["remaining_seconds"] == 2400
    assert conn.execute("SELECT COUNT(*) FROM question_assignments WHERE team_id = ?", (team_id,)).fetchone()[0] == 30
    conn.close()

@pytest.mark.parametrize("status", ["LIVE", "PAUSED", "COMPLETED"])
def test_duration_update_preserves_rounds_already_started(status):
    conn = get_db_connection()
    conn.execute("""UPDATE event_state SET event_status = ?, duration_minutes = 70,
        remaining_seconds = ?, is_paused = ?, event_start_time = '2026-10-07T09:20:00+00:00',
        event_end_time = '2026-10-07T10:30:00+00:00' WHERE id = 1""",
        (status, 0 if status == "COMPLETED" else 1800, int(status == "PAUSED")))
    conn.commit()
    before = dict(conn.execute("SELECT * FROM event_state WHERE id = 1").fetchone())
    conn.close()

    init_db()
    conn = get_db_connection()
    assert dict(conn.execute("SELECT * FROM event_state WHERE id = 1").fetchone()) == before
    conn.close()

def test_duplicate_team_name():
    team1_id, err1 = register_team("NullPointers", "Member 1", "Member 2")
    assert err1 is None
    assert team1_id is not None

    # Case-insensitive duplicate rejection
    team2_id, err2 = register_team("nullpointers", "Member 3", "Member 4")
    assert team2_id is None
    assert "already registered" in err2.lower()

def test_team_size_validation():
    # Exactly 2 members -> Valid
    t2, err2 = register_team("DuoSquad", "Lead A", "Member B")
    assert err2 is None
    assert t2 is not None

    # Exactly 3 members -> Valid
    t3, err3 = register_team("TrioSquad", "Lead A", "Member B", "Member C")
    assert err3 is None
    assert t3 is not None

    # Less than 2 members -> Invalid
    t1, err1 = register_team("SoloSquad", "Solo Lead", "")
    assert t1 is None
    assert "at least 2 members" in err1.lower()

    # Empty name -> Invalid
    t0, err0 = register_team("", "Lead A", "Member B")
    assert t0 is None
    assert "team name is required" in err0.lower()

def test_question_assignment():
    team_id, _ = register_team("CodeBreakers", "Dev 1", "Dev 2")
    assigned = get_team_assigned_questions(team_id)
    assert len(assigned) == 30

    # Q01 is unlocked immediately, subsequent questions locked
    assert assigned[0]["is_unlocked"] == 1
    assert assigned[0]["question_order"] == 1
    assert assigned[1]["is_unlocked"] == 0

    # Client question does NOT expose answers
    client_q = get_client_question(team_id, assigned[0]["id"])
    assert "code" in client_q
    assert "title" in client_q
    assert "points" in client_q
    assert "cause" not in client_q
    assert "correction" not in client_q
    assert "expected_output" not in client_q
    assert "bug_location" not in client_q

def test_question_persistence():
    team_id, _ = register_team("PersistentTeam", "Dev A", "Dev B")
    first_fetch = get_team_assigned_questions(team_id)
    # Refresh/re-query
    second_fetch = get_team_assigned_questions(team_id)
    assert [q["id"] for q in first_fetch] == [q["id"] for q in second_fetch]
    assert [q["is_unlocked"] for q in first_fetch] == [q["is_unlocked"] for q in second_fetch]
