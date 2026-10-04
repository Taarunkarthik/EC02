from datetime import datetime, timezone, timedelta
import math
import uuid
from database import get_db_connection, log_admin_action
from config import Config

def parse_iso(ts_str):
    if not ts_str:
        return None
    try:
        parsed = datetime.fromisoformat(ts_str)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def format_iso(dt):
    if not dt:
        return None
    return dt.isoformat()

def get_event_state():
    """
    Retrieves current server event state and computes remaining seconds.
    Survives page refresh, reload, and navigation.
    States:
      - 'WAITING': Before admin starts competition.
      - 'LIVE': Active debugging competition.
      - 'PAUSED': Temporarily paused.
      - 'COMPLETED': Competition concluded.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM event_state WHERE id = 1")
    row = cur.fetchone()

    if not row:
        cfg = Config.load_event_config()
        dur = cfg.get("duration_minutes", 40)
        conn.close()
        return {
            "event_status": "WAITING",
            "current_state": "WAITING",
            "duration_minutes": dur,
            "remaining_seconds": dur * 60,
            "formatted_time": f"{dur:02d}:00",
            "is_paused": 0
        }

    state = dict(row)
    now = datetime.now(timezone.utc)
    status = state.get("event_status", "WAITING")
    is_paused = bool(state.get("is_paused", 0))
    remaining = state.get("remaining_seconds", state.get("duration_minutes", 40) * 60)

    # If LIVE and not paused, compute dynamic remaining time from server clock
    if status == "LIVE" and not is_paused and state.get("event_end_time"):
        end_dt = parse_iso(state["event_end_time"])
        if end_dt:
            diff = (end_dt - now).total_seconds()
            if diff <= 0:
                # Timer expired! Automatically transition to COMPLETED
                remaining = 0
                status = "COMPLETED"
                cur.execute("""
                    UPDATE event_state 
                    SET event_status = 'COMPLETED', remaining_seconds = 0 
                    WHERE id = 1 AND event_status = 'LIVE' AND is_paused = 0 AND event_end_time = ?
                """, (state["event_end_time"],))
                changed = cur.rowcount
                conn.commit()
                if not changed:
                    conn.close()
                    return get_event_state()
                log_admin_action("TIMER_EXPIRED", "Debugging timer reached zero. Competition completed.")
            else:
                remaining = math.ceil(diff)

    conn.close()

    mins = remaining // 60
    secs = remaining % 60
    state["event_status"] = status
    state["current_state"] = status  # alias for backwards compatibility
    state["remaining_seconds"] = remaining
    state["formatted_time"] = f"{mins:02d}:{secs:02d}"
    return state

def start_event():
    """Starts the debugging competition for the configured duration."""
    cfg = Config.load_event_config()
    duration = cfg.get("duration_minutes", 40)
    now = datetime.now(timezone.utc)
    end_dt = now + timedelta(minutes=duration)

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT event_status FROM event_state WHERE id = 1").fetchone()[0] != "WAITING":
            return False, "The event has already started. Resume a paused event or reset before restarting."
        conn.execute("""
            UPDATE event_state 
            SET event_status = 'LIVE',
                event_start_time = ?,
                event_end_time = ?,
                duration_minutes = ?,
                is_paused = 0,
                pause_time = NULL,
                remaining_seconds = ?
            WHERE id = 1
        """, (format_iso(now), format_iso(end_dt), duration, duration * 60))
        conn.commit()
        log_admin_action("START_EVENT", f"Competition started. {duration}-minute timer active until {end_dt.isoformat()}.")
        return True, "Competition started! All teams can now access challenges."
    except Exception as e:
        conn.rollback()
        return False, "The event action could not be saved. Please try again."
    finally:
        conn.close()


def restart_event():
    """Restart the event clock without deleting teams or competition records."""
    cfg = Config.load_event_config()
    duration = cfg.get("duration_minutes", 40)
    now = datetime.now(timezone.utc)
    end_dt = now + timedelta(minutes=duration)

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE event_state
            SET event_status = 'LIVE',
                event_start_time = ?,
                event_end_time = ?,
                duration_minutes = ?,
                is_paused = 0,
                pause_time = NULL,
                remaining_seconds = ?
            WHERE id = 1
        """, (format_iso(now), format_iso(end_dt), duration, duration * 60))
        conn.execute("UPDATE competition_controls SET quiz_status = 'WAITING', results_published = 0 WHERE id = 1")
        conn.commit()
        log_admin_action("RESTART_EVENT", f"Competition restarted. {duration}-minute timer active until {end_dt.isoformat()}.")
        return True, "Competition restarted. Existing teams and submissions were preserved."
    except Exception:
        conn.rollback()
        return False, "The event could not be restarted. Please try again."
    finally:
        conn.close()

def pause_event():
    """Pauses the active competition and preserves remaining time."""
    state = get_event_state()
    if state["event_status"] == "PAUSED" or state["is_paused"]:
        return False, "Event is already paused."
    if state["event_status"] != "LIVE":
        return False, f"Cannot pause event in status '{state['event_status']}'."

    now = datetime.now(timezone.utc)
    remaining = state["remaining_seconds"]

    conn = get_db_connection()
    try:
        result = conn.execute("""
            UPDATE event_state 
            SET event_status = 'PAUSED',
                is_paused = 1,
                pause_time = ?,
                remaining_seconds = ?
            WHERE id = 1 AND event_status = 'LIVE' AND event_end_time = ?
        """, (format_iso(now), remaining, state["event_end_time"]))
        if not result.rowcount:
            return False, "Event state changed. Refresh the controls and try again."
        conn.commit()
        log_admin_action("PAUSE_EVENT", f"Event paused with {remaining} seconds remaining.")
        return True, "Competition paused."
    except Exception as e:
        conn.rollback()
        return False, "The event action could not be saved. Please try again."
    finally:
        conn.close()

def resume_event():
    """Resumes competition and recalculates end time based on remaining seconds."""
    state = get_event_state()
    if state["event_status"] != "PAUSED":
        return False, "Event is not currently paused."

    now = datetime.now(timezone.utc)
    remaining = state["remaining_seconds"]
    new_end_dt = now + timedelta(seconds=remaining)

    conn = get_db_connection()
    try:
        result = conn.execute("""
            UPDATE event_state 
            SET event_status = 'LIVE',
                is_paused = 0,
                pause_time = NULL,
                event_end_time = ?
            WHERE id = 1 AND event_status = 'PAUSED'
        """, (format_iso(new_end_dt),))
        if not result.rowcount:
            return False, "Event state changed. Refresh the controls and try again."
        conn.commit()
        log_admin_action("RESUME_EVENT", f"Event resumed with {remaining} seconds remaining.")
        return True, "Competition resumed."
    except Exception as e:
        conn.rollback()
        return False, "The event action could not be saved. Please try again."
    finally:
        conn.close()

def end_event():
    """Immediately ends the competition and locks all submissions."""
    now = datetime.now(timezone.utc)
    conn = get_db_connection()
    try:
        conn.execute("""
            UPDATE event_state 
            SET event_status = 'COMPLETED',
                is_paused = 0,
                pause_time = NULL,
                remaining_seconds = 0
            WHERE id = 1
        """)
        conn.commit()
        log_admin_action("END_EVENT", f"Competition ended manually at {now.isoformat()}.")
        return True, "Competition concluded. All submissions are locked."
    except Exception as e:
        conn.rollback()
        return False, "The event action could not be saved. Please try again."
    finally:
        conn.close()

def reset_event_data(confirmation):
    """
    Safely purges event progress (teams, participants, submissions, powerups, scores).
    Requires typing 'RESET EVENT' exactly as specified in Section 28.
    """
    if not isinstance(confirmation, str) or confirmation.strip() != "RESET EVENT":
        return False, "Confirmation failed. You must type 'RESET EVENT' exactly to proceed."

    cfg = Config.load_event_config()
    dur = cfg.get("duration_minutes", 40)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("DELETE FROM quiz_answers")
        cur.execute("DELETE FROM quiz_sessions")
        cur.execute("DELETE FROM team_activity")
        cur.execute("DELETE FROM activity_events")
        cur.execute("DELETE FROM submissions")
        cur.execute("DELETE FROM powerups")
        cur.execute("DELETE FROM question_assignments")
        cur.execute("DELETE FROM scores")
        cur.execute("DELETE FROM participants")
        cur.execute("DELETE FROM teams")
        
        cur.execute("""
            UPDATE event_state 
            SET event_status = 'WAITING',
                event_start_time = NULL,
                event_end_time = NULL,
                duration_minutes = ?,
                is_paused = 0,
                pause_time = NULL,
                remaining_seconds = ?
            WHERE id = 1
        """, (dur, dur * 60))
        cur.execute("UPDATE competition_controls SET quiz_status = 'WAITING', results_published = 0, generation = ? WHERE id = 1", (uuid.uuid4().hex,))
        conn.commit()
        log_admin_action("RESET_EVENT", "Tournament data completely reset to initial state.")
        return True, "Event data successfully reset to initial state."
    except Exception as e:
        conn.rollback()
        return False, "The event action could not be saved. Please try again."
    finally:
        conn.close()
