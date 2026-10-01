import pytest
from database import init_db, get_db_connection, register_team, get_team_assigned_questions
from event_manager import reset_event_data
from scoring import (
    process_submission, evaluate_submission, activate_rubber_duck,
    activate_git_revert, arm_double_commit
)

@pytest.fixture(autouse=True)
def setup_clean_db():
    init_db(force_reset=True)
    yield
    reset_event_data("RESET EVENT")

def test_submission():
    team_id, _ = register_team("ScoringTeam", "Member 1", "Member 2")
    submission_data = {
        "error_location": "Line 3",
        "error_type": "Logical Error",
        "expected_output": "10",
        "cause": "The loop stops before processing the last element due to len(numbers) - 1.",
        "correction": "Use range(len(numbers)) instead."
    }

    result, err = process_submission(team_id, "Q01", submission_data)
    assert err is None
    assert result is not None
    assert result["total_score"] >= 15.0

    # Verify score persisted in scores table
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT score, completed_count FROM scores WHERE team_id = ?", (team_id,))
    sc = cur.fetchone()
    assert sc["score"] == result["total_score"]
    assert sc["completed_count"] == 1

    # Verify next question (Q02) is unlocked
    cur.execute("""
        SELECT is_unlocked FROM question_assignments 
        WHERE team_id = ? AND question_order = 2
    """, (team_id,))
    assert cur.fetchone()["is_unlocked"] == 1
    conn.close()

def test_partial_scoring():
    sample_question = {
        "id": "Q01",
        "points": 20,
        "error_type": "Logical Error",
        "bug_location": "Line 3",
        "cause": "The loop stops before processing the last element.",
        "expected_output": "10",
        "correction": "Use range(len(numbers))"
    }

    # Only correct error type & bug location (25% = 5 points)
    partial_sub = {
        "error_location": "Line 3",
        "error_type": "Logical Error",
        "expected_output": "wrong output",
        "cause": "unrelated explanation",
        "correction": "wrong fix"
    }
    res = evaluate_submission(sample_question, partial_sub)
    assert res["error_type_score"] == 3.0  # 15%
    assert res["error_loc_score"] == 2.0   # 10%
    assert res["total_score"] == 5.0
    assert res["total_score"] < 20.0

def test_duplicate_submission():
    team_id, _ = register_team("DupTeam", "M1", "M2")
    sub1 = {
        "error_location": "Line 3",
        "error_type": "Logical Error",
        "expected_output": "10",
        "cause": "Loop stops early",
        "correction": "Use range(len(numbers))"
    }
    res1, err1 = process_submission(team_id, "Q01", sub1)
    assert err1 is None

    # Second submission on same question
    sub2 = {
        "error_location": "Line 3",
        "error_type": "Logical Error",
        "expected_output": "10",
        "cause": "Loop boundary is off by one",
        "correction": "Iterate full length"
    }
    res2, err2 = process_submission(team_id, "Q01", sub2)
    assert err2 is None

    # Scores table should take the highest score for that question
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT score FROM scores WHERE team_id = ?", (team_id,))
    total_score = cur.fetchone()["score"]
    assert total_score == max(res1["total_score"], res2["total_score"])
    conn.close()

def test_rubber_duck():
    team_id, _ = register_team("DuckTeam", "Duck1", "Duck2")
    
    # 1. Activate Rubber Duck
    ok, msg, hint = activate_rubber_duck(team_id, "Q01")
    assert ok is True
    assert hint is not None
    assert "range" in hint.lower() or "limit" in hint.lower()

    # 2. Cannot reuse Rubber Duck
    ok2, msg2, _ = activate_rubber_duck(team_id, "Q02")
    assert ok2 is False
    assert "already been used" in msg2.lower()

    # 3. Verify 10% deduction applied upon submission
    sub = {
        "error_location": "Line 3",
        "error_type": "Logical Error",
        "expected_output": "10",
        "cause": "The loop stops before processing the last element due to len(numbers) - 1.",
        "correction": "Use range(len(numbers)) instead."
    }
    res, err = process_submission(team_id, "Q01", sub)
    assert err is None
    assert res["hint_used"] == 1
    # Deduction of 2 points (10% of 20)
    assert res["total_score"] == pytest.approx(res["raw_total"] - 2.0, abs=0.1)

def test_git_revert():
    team_id, _ = register_team("RevertTeam", "Rev1", "Rev2")
    
    # Activate Git Revert on Q01
    ok, msg, new_qid = activate_git_revert(team_id, "Q01")
    assert ok is True
    assert new_qid != "Q01"

    # Verify Q01 is marked abandoned and cannot be completed
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_abandoned, is_unlocked FROM question_assignments WHERE team_id = ? AND question_id = 'Q01'", (team_id,))
    asgn = cur.fetchone()
    assert asgn["is_abandoned"] == 1
    assert asgn["is_unlocked"] == 0

    # Cannot reuse Git Revert
    ok2, msg2, _ = activate_git_revert(team_id, new_qid)
    assert ok2 is False
    assert "already been used" in msg2.lower()
    conn.close()

def test_double_commit():
    team_id, _ = register_team("DoubleTeam", "Double1", "Double2")

    # Arm Double Commit on Q01
    ok, msg = arm_double_commit(team_id, "Q01")
    assert ok is True

    # 1. Correct answer receives 2x points
    accurate_sub = {
        "error_location": "Line 3",
        "error_type": "Logical Error",
        "expected_output": "10",
        "cause": "The loop stops before processing the last element due to len(numbers) - 1.",
        "correction": "Use range(len(numbers)) instead."
    }
    res, err = process_submission(team_id, "Q01", accurate_sub)
    assert err is None
    assert res["is_double_commit"] == 1
    assert res["total_score"] >= 30.0  # 2x multiplier

    # Double commit is now consumed
    ok2, msg2 = arm_double_commit(team_id, "Q02")
    assert ok2 is False
    assert "already been used" in msg2.lower()

def test_score_calculation():
    team_id, _ = register_team("MultiScoreTeam", "M1", "M2")
    
    # Solve Q01
    sub1 = {
        "error_location": "Line 3",
        "error_type": "Logical Error",
        "expected_output": "10",
        "cause": "The loop stops before processing the last element.",
        "correction": "Use range(len(numbers)) instead."
    }
    res1, _ = process_submission(team_id, "Q01", sub1)

    # Solve Q02
    sub2 = {
        "error_location": "Line 4",
        "error_type": "Syntax Error",
        "expected_output": "Count is 10",
        "cause": "Missing semicolon delimiter",
        "correction": "int count = 10;"
    }
    res2, _ = process_submission(team_id, "Q02", sub2)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT score, completed_count FROM scores WHERE team_id = ?", (team_id,))
    row = cur.fetchone()
    assert row["completed_count"] == 2
    assert row["score"] == pytest.approx(res1["total_score"] + res2["total_score"], abs=0.1)
    conn.close()
