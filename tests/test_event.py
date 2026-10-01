import pytest
from database import init_db, get_db_connection, register_team
from event_manager import (
    get_event_state, start_event, pause_event, resume_event,
    end_event, reset_event_data
)

@pytest.fixture(autouse=True)
def setup_clean_db():
    init_db(force_reset=True)
    yield
    reset_event_data("RESET EVENT")

def test_event_start():
    state_before = get_event_state()
    assert state_before["event_status"] == "WAITING"

    ok, msg = start_event()
    assert ok is True
    assert "started" in msg.lower()

    state_after = get_event_state()
    assert state_after["event_status"] == "LIVE"
    assert state_after["duration_minutes"] == 70
    assert state_after["remaining_seconds"] > 0
    assert state_after["remaining_seconds"] <= 4200
    assert state_after["is_paused"] == 0

def test_event_pause():
    start_event()
    ok, msg = pause_event()
    assert ok is True

    state = get_event_state()
    assert state["event_status"] == "PAUSED"
    assert state["is_paused"] == 1
    rem = state["remaining_seconds"]
    assert rem > 0

    # Cannot pause already paused event
    ok2, msg2 = pause_event()
    assert ok2 is False
    assert "already paused" in msg2.lower()

def test_event_resume():
    start_event()
    pause_event()
    
    ok, msg = resume_event()
    assert ok is True
    assert "resumed" in msg.lower()

    state = get_event_state()
    assert state["event_status"] == "LIVE"
    assert state["is_paused"] == 0

def test_timer_persistence():
    start_event()
    first_check = get_event_state()
    assert first_check["event_status"] == "LIVE"
    end_time_1 = first_check["event_end_time"]

    # Re-fetch state (simulating page reload or app restart)
    second_check = get_event_state()
    assert second_check["event_status"] == "LIVE"
    assert second_check["event_end_time"] == end_time_1
    assert abs(first_check["remaining_seconds"] - second_check["remaining_seconds"]) <= 2

def test_event_completion():
    start_event()
    ok, msg = end_event()
    assert ok is True

    state = get_event_state()
    assert state["event_status"] == "COMPLETED"
    assert state["remaining_seconds"] == 0

def test_event_reset():
    team_id, _ = register_team("ResetCandidate", "M1", "M2")
    start_event()

    # Wrong confirmation string fails
    ok_fail, msg_fail = reset_event_data("WRONG CONFIRMATION")
    assert ok_fail is False
    assert "RESET EVENT" in msg_fail

    # Correct confirmation succeeds
    ok, msg = reset_event_data("RESET EVENT")
    assert ok is True

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM teams")
    assert cur.fetchone()["c"] == 0

    state = get_event_state()
    assert state["event_status"] == "WAITING"
    assert state["remaining_seconds"] == 4200
    conn.close()
