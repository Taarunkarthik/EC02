from datetime import datetime, timezone, timedelta
from database import get_db_connection, log_admin_action
from config import Config

def parse_iso(ts_str):
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str)
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
      - 'LIVE': Active 70-minute competition.
      - 'PAUSED': Temporarily paused.
      - 'COMPLETED': Competition concluded.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM event_state WHERE id = 1")
    row = cur.fetchone()

    if not row:
        cfg = Config.load_event_config()
        dur = cfg.get("duration_minutes", 70)
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
    remaining = state.get("remaining_seconds", 4200)

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
                    WHERE id = 1
                """)
                conn.commit()
                log_admin_action("TIMER_EXPIRED", "70-minute event timer reached zero. Competition completed.")
            else:
                remaining = int(diff)

    conn.close()

    mins = remaining // 60
    secs = remaining % 60
    state["event_status"] = status
    state["current_state"] = status  # alias for backwards compatibility
    state["remaining_seconds"] = remaining
    state["formatted_time"] = f"{mins:02d}:{secs:02d}"
    return state

def start_event():
    """Starts the 70-minute competition."""
    cfg = Config.load_event_config()
    duration = cfg.get("duration_minutes", 70)
    now = datetime.now(timezone.utc)
    end_dt = now + timedelta(minutes=duration)

    conn = get_db_connection()
    try:
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
        log_admin_action("START_EVENT", f"Competition started. 70-minute timer active until {end_dt.isoformat()}.")
        return True, "Competition started! All teams can now access challenges."
    except Exception as e:
        conn.rollback()
        return False, str(e)
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
        conn.execute("""
            UPDATE event_state 
            SET event_status = 'PAUSED',
                is_paused = 1,
                pause_time = ?,
                remaining_seconds = ?
            WHERE id = 1
        """, (format_iso(now), remaining))
        conn.commit()
        log_admin_action("PAUSE_EVENT", f"Event paused with {remaining} seconds remaining.")
        return True, "Competition paused."
    except Exception as e:
        conn.rollback()
        return False, str(e)
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
        conn.execute("""
            UPDATE event_state 
            SET event_status = 'LIVE',
                is_paused = 0,
                pause_time = NULL,
                event_end_time = ?
            WHERE id = 1
        """, (format_iso(new_end_dt),))
        conn.commit()
        log_admin_action("RESUME_EVENT", f"Event resumed with {remaining} seconds remaining.")
        return True, "Competition resumed."
    except Exception as e:
        conn.rollback()
        return False, str(e)
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
        return False, str(e)
    finally:
        conn.close()

def reset_event_data(confirmation):
    """
    Safely purges event progress (teams, participants, submissions, powerups, scores).
    Requires typing 'RESET EVENT' exactly as specified in Section 28.
    """
    if confirmation.strip() != "RESET EVENT" and confirmation.strip() != "RESET":
        return False, "Confirmation failed. You must type 'RESET EVENT' exactly to proceed."

    cfg = Config.load_event_config()
    dur = cfg.get("duration_minutes", 70)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
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
        conn.commit()
        log_admin_action("RESET_EVENT", "Tournament data completely reset to initial state.")
        return True, "Event data successfully reset to initial state."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
