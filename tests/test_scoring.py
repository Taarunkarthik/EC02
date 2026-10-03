import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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
    assert res2 is None
    assert "already been answered" in err2

    # The first answer is final, including partial or incorrect answers.
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT score FROM scores WHERE team_id = ?", (team_id,))
    total_score = cur.fetchone()["score"]
    assert total_score == res1["total_score"]
    assert cur.execute("SELECT COUNT(*) FROM submissions WHERE team_id = ?", (team_id,)).fetchone()[0] == 1
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


def reference_answer(question):
    return {"error_location": question["bug_location"], "error_type": question["error_type"],
            "expected_output": question["expected_output"], "cause": question["cause"],
            "correction": question["correction"]}


def sample_question():
    return {"points": 20, "error_type": "Logical Error", "bug_location": "Line 3",
            "expected_output": "10", "cause": "The loop stops before the last element.",
            "correction": "Use range(len(numbers)) instead.",
            "cause_keywords": ["loop", "last", "element"],
            "correction_keywords": ["range", "len", "numbers"]}


@pytest.mark.parametrize("field,token", [("cause", "loop"), ("correction", "range")])
@pytest.mark.parametrize("repeat", [1, 5])
def test_descriptive_answer_requires_two_distinct_keywords(field, token, repeat):
    question = sample_question()
    submission = reference_answer(question)
    submission[field] = " ".join([token] * repeat)
    result = evaluate_submission(question, submission)
    assert result[f"{field}_score"] == 0
    assert result["keyword_matches"][field] == 1
    assert result["answer_status"] == "partial"


def test_keyword_matching_uses_boundaries_and_deduplicates_reference_entries():
    question = sample_question()
    question["cause_keywords"] = json.dumps(["loop", "LOOP", "last"])
    submission = reference_answer(question)
    submission["cause"] = "loop loop elastic"
    result = evaluate_submission(question, submission)
    assert result["cause_score"] == 0
    assert result["keyword_matches"]["cause"] == 1
    submission["cause"] = "LOOP misses the LAST item"
    assert evaluate_submission(question, submission)["cause_score"] > 0


def test_legacy_reference_fallback_ignores_stopwords():
    question = sample_question()
    question.pop("cause_keywords")
    submission = reference_answer(question)
    submission["cause"] = "the loop"
    assert evaluate_submission(question, submission)["cause_score"] == 0
    submission["cause"] = "the last loop"
    assert evaluate_submission(question, submission)["cause_score"] > 0


@pytest.mark.parametrize("hint,swap,double", [
    (False, False, False), (True, False, False), (False, True, False), (True, True, False),
    (False, False, True), (True, False, True), (False, True, True), (True, True, True),
])
def test_modifiers_are_consistent_and_visible(hint, swap, double):
    question = sample_question()
    result = evaluate_submission(question, reference_answer(question), double, hint, swap)
    assert result["raw_total"] == result["raw_score"] == 20
    assert result["total_score"] == (40 if double else 20) - (2 if hint else 0) - (2 if swap else 0)
    assert result["max_score"] == result["total_score"]
    assert result["penalties"]["hint"] == (2 if hint else 0)
    assert result["penalties"]["swap"] == (2 if swap else 0)
    assert result["answer_status"] == "correct"  # Penalties do not mark a correct answer wrong.


def test_penalties_never_create_negative_points_or_a_double_commit_reward():
    question = sample_question()
    submission = {"error_type": "Logical Error"}
    result = evaluate_submission(question, submission, hint_used=True, swap_used=True)
    assert result["raw_score"] == 3
    assert result["total_score"] == 0
    assert result["penalties"]["applied"] == 3
    double = evaluate_submission(question, submission, is_double_commit=True, hint_used=True, swap_used=True)
    assert double["total_score"] == 0
    assert double["penalties"]["applied"] == 0
    assert evaluate_submission(question, {})["answer_status"] == "incorrect"


@pytest.mark.parametrize("expected,wrong", [("10", "1"), ("-1", "1"), ("1.5", "15"), ("[1, 2]", "[1, 3]")])
def test_short_output_must_match_including_sign_and_decimal(expected, wrong):
    question = sample_question()
    question["expected_output"] = expected
    assert evaluate_submission(question, {"expected_output": wrong})["output_score"] == 0
    assert evaluate_submission(question, {"expected_output": expected})["output_score"] == 4


def test_generic_error_and_all_line_numbers_do_not_identify_bug():
    result = evaluate_submission(sample_question(), {"error_type": "error", "error_location": "1 2 3 4 5"})
    assert result["error_type_score"] == result["error_loc_score"] == 0


def test_incorrect_answer_is_final_and_cannot_use_powerups_afterward():
    team_id, _ = register_team("Final incorrect", "One", "Two")
    first, error = process_submission(team_id, "Q01", {})
    assert error is None and first["answer_status"] == "incorrect"
    second, error = process_submission(team_id, "Q01", reference_answer(sample_question()))
    assert second is None and "already been answered" in error
    for powerup in (activate_rubber_duck, activate_git_revert, arm_double_commit):
        assert powerup(team_id, "Q01")[0] is False
    conn = get_db_connection()
    assert conn.execute("SELECT SUM(is_used) + SUM(is_armed) FROM powerups WHERE team_id = ?", (team_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT is_unlocked FROM question_assignments WHERE team_id = ? AND question_id = 'Q02'", (team_id,)).fetchone()[0] == 1
    conn.close()


def test_concurrent_different_requests_accept_exactly_one_answer():
    team_id, _ = register_team("Concurrent final answer", "One", "Two")
    ready = Barrier(6)

    def submit(index):
        ready.wait(timeout=5)
        return process_submission(team_id, "Q01", dict(reference_answer(sample_question()), request_id=f"concurrent-{index}"))

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(submit, range(6)))
    assert sum(error is None for _, error in results) == 1
    assert all("already been answered" in error for _, error in results if error)
    conn = get_db_connection()
    assert conn.execute("SELECT COUNT(*) FROM submissions WHERE team_id = ?", (team_id,)).fetchone()[0] == 1
    assert conn.execute("SELECT completed_count FROM scores WHERE team_id = ?", (team_id,)).fetchone()[0] == 1
    conn.close()


@pytest.mark.parametrize("unassigned_candidate", [False, True])
@pytest.mark.parametrize("hint_timing", ["none", "before", "after"])
def test_swap_penalty_is_persisted_on_replacement_and_hint_cannot_be_escaped(unassigned_candidate, hint_timing):
    team_id, _ = register_team("Replacement modifiers", "One", "Two")
    if unassigned_candidate:
        conn = get_db_connection()
        conn.execute("""INSERT INTO questions (id, language, title, difficulty, code, error_type, bug_location,
                     expected_output, cause, correction, points, hint, is_active)
                     SELECT 'Q99', language, title, difficulty, code, error_type, bug_location,
                     expected_output, cause, correction, points, hint, is_active FROM questions WHERE id = 'Q01'""")
        conn.commit()
        conn.close()
    if hint_timing == "before":
        assert activate_rubber_duck(team_id, "Q01")[0]
    ok, _, replacement = activate_git_revert(team_id, "Q01")
    assert ok and replacement != "Q01"
    if hint_timing == "after":
        assert activate_rubber_duck(team_id, replacement)[0]
    assert process_submission(team_id, "Q01", {})[1]  # Abandoned answer is never accepted.
    conn = get_db_connection()
    question = dict(conn.execute("SELECT * FROM questions WHERE id = ?", (replacement,)).fetchone())
    conn.close()
    first, error = process_submission(team_id, replacement, dict(reference_answer(question), request_id="replacement-submit"))
    assert error is None and first["swap_used"] == 1
    assert first["hint_used"] == int(hint_timing != "none")
    expected = question["points"] * (0.8 if hint_timing != "none" else 0.9)
    assert first["total_score"] == pytest.approx(expected)
    retry, error = process_submission(team_id, replacement, {"request_id": "replacement-submit", "cause": "changed"})
    assert error is None and retry == first
    conn = get_db_connection()
    record = conn.execute("SELECT total_score, response_json FROM submissions WHERE team_id = ?", (team_id,)).fetchone()
    assert record["total_score"] == pytest.approx(expected)
    assert json.loads(record["response_json"])["penalties"] == first["penalties"]
    next_question = dict(conn.execute("SELECT * FROM questions WHERE id = 'Q02'").fetchone())
    conn.close()
    next_result, error = process_submission(team_id, "Q02", reference_answer(next_question))
    assert error is None and next_result["swap_used"] == next_result["hint_used"] == 0


def test_all_seed_reference_answers_can_receive_full_credit():
    conn = get_db_connection()
    questions = [dict(row) for row in conn.execute("SELECT * FROM questions")]
    conn.close()
    for question in questions:
        result = evaluate_submission(question, reference_answer(question))
        assert result["total_score"] == question["points"], question["id"]
        assert result["answer_status"] == "correct"
