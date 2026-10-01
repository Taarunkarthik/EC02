import re
from rapidfuzz import fuzz
from database import get_db_connection, unlock_next_question
from config import Config

def normalize_text(text):
    if not text:
        return ""
    text = str(text).strip().lower()
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_line_numbers(text):
    if not text:
        return []
    matches = re.findall(r'(?:line\s*|l)?(\d+)', str(text).lower())
    return [int(m) for m in matches if m.isdigit()]

def evaluate_submission(question, user_submission, is_double_commit=False, hint_used=False):
    """
    Evaluates participant submission against reference question data.
    Weights per Section 19:
      - Error Identification: 25% (Error Type 15%, Bug Location 10%)
      - Cause Explanation:    25%
      - Expected Output:      20%
      - Correction:           30%
    """
    base_points = float(question.get("points", question.get("base_points", 20)))

    # 1. Error Type (15% of base)
    ref_error_type = normalize_text(question.get("error_type", ""))
    user_error_type = normalize_text(user_submission.get("error_type", ""))
    type_score = 0.0
    if user_error_type:
        if user_error_type == ref_error_type or user_error_type in ref_error_type or ref_error_type in user_error_type:
            type_score = 0.15 * base_points
        elif fuzz.ratio(user_error_type, ref_error_type) >= 70:
            type_score = 0.15 * base_points

    # 2. Bug Location (10% of base)
    ref_loc_lines = extract_line_numbers(question.get("bug_location", ""))
    user_loc_lines = extract_line_numbers(user_submission.get("error_location", ""))
    loc_score = 0.0
    if ref_loc_lines and user_loc_lines and any(line in ref_loc_lines for line in user_loc_lines):
        loc_score = 0.10 * base_points
    else:
        norm_ref_loc = normalize_text(question.get("bug_location", ""))
        norm_user_loc = normalize_text(user_submission.get("error_location", ""))
        if norm_user_loc and (norm_user_loc in norm_ref_loc or norm_ref_loc in norm_user_loc):
            loc_score = 0.10 * base_points
        elif fuzz.partial_ratio(norm_user_loc, norm_ref_loc) >= 75:
            loc_score = 0.10 * base_points

    error_id_score = type_score + loc_score

    # 3. Cause Explanation (25% of base)
    ref_cause = normalize_text(question.get("cause", ""))
    user_cause = normalize_text(user_submission.get("cause", ""))
    cause_score = 0.0
    if user_cause:
        ratio = fuzz.token_set_ratio(user_cause, ref_cause)
        if ratio >= 65:
            cause_score = 0.25 * base_points
        elif ratio >= 45:
            cause_score = 0.15 * base_points

    # 4. Expected Output (20% of base)
    ref_output = normalize_text(question.get("expected_output", ""))
    user_output = normalize_text(user_submission.get("expected_output", ""))
    output_score = 0.0
    if user_output:
        if user_output == ref_output or user_output in ref_output or ref_output in user_output:
            output_score = 0.20 * base_points
        else:
            out_ratio = fuzz.token_sort_ratio(user_output, ref_output)
            if out_ratio >= 70:
                output_score = 0.20 * base_points
            elif out_ratio >= 50:
                output_score = 0.10 * base_points

    # 5. Correction (30% of base)
    ref_corr = normalize_text(question.get("correction", ""))
    user_corr = normalize_text(user_submission.get("correction", ""))
    corr_score = 0.0
    if user_corr:
        corr_ratio = fuzz.token_set_ratio(user_corr, ref_corr)
        if corr_ratio >= 65:
            corr_score = 0.30 * base_points
        elif corr_ratio >= 45:
            corr_score = 0.15 * base_points

    raw_total = error_id_score + cause_score + output_score + corr_score
    final_total = raw_total

    # Tactical Modifiers
    if is_double_commit:
        if raw_total >= (0.60 * base_points):
            final_total = raw_total * 2.0
        else:
            final_total = 0.0

    if hint_used and final_total > 0:
        penalty = 0.10 * base_points
        final_total = max(0.0, final_total - penalty)

    return {
        "error_type_score": round(type_score, 2),
        "error_loc_score": round(loc_score, 2),
        "cause_score": round(cause_score, 2),
        "output_score": round(output_score, 2),
        "correction_score": round(corr_score, 2),
        "raw_total": round(raw_total, 2),
        "total_score": round(final_total, 2),
        "base_points": base_points,
        "is_double_commit": 1 if is_double_commit else 0,
        "hint_used": 1 if hint_used else 0,
        "percentage": round((raw_total / base_points) * 100, 1) if base_points > 0 else 0
    }

def process_submission(team_id, question_id, submission_data):
    """
    Validates, scores, persists submission and updates progression and team score.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if question exists
        cur.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
        question = cur.fetchone()
        if not question:
            return None, "Question not found."

        # Check question assignment
        cur.execute("""
            SELECT * FROM question_assignments 
            WHERE team_id = ? AND question_id = ? AND is_abandoned = 0
        """, (team_id, question_id))
        assignment = cur.fetchone()
        if not assignment:
            return None, "This question is not currently assigned to your team."

        # Check if Double Commit is armed
        cur.execute("""
            SELECT * FROM powerups 
            WHERE team_id = ? AND powerup_type = 'DOUBLE_COMMIT' AND is_armed = 1 AND target_question_id = ?
        """, (team_id, question_id))
        double_armed = cur.fetchone()
        is_double = bool(double_armed)

        # Check if Rubber Duck was used
        cur.execute("""
            SELECT * FROM powerups 
            WHERE team_id = ? AND powerup_type = 'RUBBER_DUCK' AND is_used = 1 AND target_question_id = ?
        """, (team_id, question_id))
        duck_used = cur.fetchone()
        is_hint = bool(duck_used)

        # Evaluate score
        eval_result = evaluate_submission(
            dict(question), 
            submission_data, 
            is_double_commit=is_double, 
            hint_used=is_hint
        )

        # Record submission in SQLite
        cur.execute("""
            INSERT INTO submissions (
                team_id, question_id, error_location, error_type, expected_output, cause, correction,
                error_loc_score, error_type_score, cause_score, output_score, correction_score,
                total_score, is_double_commit, is_accepted, submitted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        """, (
            team_id, question_id,
            submission_data.get("error_location", ""),
            submission_data.get("error_type", ""),
            submission_data.get("expected_output", ""),
            submission_data.get("cause", ""),
            submission_data.get("correction", ""),
            eval_result["error_loc_score"],
            eval_result["error_type_score"],
            eval_result["cause_score"],
            eval_result["output_score"],
            eval_result["correction_score"],
            eval_result["total_score"],
            eval_result["is_double_commit"]
        ))

        # Mark question as completed
        cur.execute("""
            UPDATE question_assignments 
            SET is_completed = 1 
            WHERE team_id = ? AND question_id = ?
        """, (team_id, question_id))

        # Unlock next question in sequence
        unlock_next_question(team_id, assignment["question_order"], cur)

        # Consume Double Commit if armed
        if is_double:
            cur.execute("""
                UPDATE powerups 
                SET is_used = 1, is_armed = 0, used_at = CURRENT_TIMESTAMP 
                WHERE team_id = ? AND powerup_type = 'DOUBLE_COMMIT'
            """, (team_id,))

        # Update Team's Total Score & Completed Count in scores table
        cur.execute("""
            SELECT COALESCE(SUM(max_score), 0) as total_debug, COUNT(DISTINCT question_id) as comp_count
            FROM (
                SELECT question_id, MAX(total_score) as max_score
                FROM submissions
                WHERE team_id = ? AND is_accepted = 1
                GROUP BY question_id
            )
        """, (team_id,))
        stats = cur.fetchone()
        total_score = stats["total_debug"] or 0.0
        comp_count = stats["comp_count"] or 0

        cur.execute("""
            UPDATE scores 
            SET score = ?, completed_count = ?, last_submission_time = CURRENT_TIMESTAMP, last_updated = CURRENT_TIMESTAMP 
            WHERE team_id = ?
        """, (total_score, comp_count, team_id))

        conn.commit()
        return eval_result, None
    except Exception as e:
        conn.rollback()
        return None, str(e)
    finally:
        conn.close()

def activate_rubber_duck(team_id, question_id):
    """Activates Rubber Duck hint for target question."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT is_used FROM powerups WHERE team_id = ? AND powerup_type = 'RUBBER_DUCK'", (team_id,))
        row = cur.fetchone()
        if not row:
            return False, "Power-up not found.", None
        if row["is_used"]:
            return False, "Rubber Duck has already been used by your team.", None

        cur.execute("SELECT hint FROM questions WHERE id = ?", (question_id,))
        q = cur.fetchone()
        hint = q["hint"] if q and q["hint"] else "Review the line boundaries and logic conditions."

        cur.execute("""
            UPDATE powerups 
            SET is_used = 1, used_at = CURRENT_TIMESTAMP, target_question_id = ?
            WHERE team_id = ? AND powerup_type = 'RUBBER_DUCK'
        """, (question_id, team_id))
        conn.commit()
        return True, "Rubber Duck activated (-10% points penalty).", hint
    except Exception as e:
        conn.rollback()
        return False, str(e), None
    finally:
        conn.close()

def activate_git_revert(team_id, question_id):
    """
    Abandons current question and swaps it for another active question not yet assigned.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT is_used FROM powerups WHERE team_id = ? AND powerup_type = 'GIT_REVERT'", (team_id,))
        row = cur.fetchone()
        if not row:
            return False, "Power-up not found.", None
        if row["is_used"]:
            return False, "Git Revert has already been used by your team.", None

        cur.execute("""
            SELECT question_order, is_completed 
            FROM question_assignments 
            WHERE team_id = ? AND question_id = ? AND is_abandoned = 0
        """, (team_id, question_id))
        asgn = cur.fetchone()
        if not asgn:
            return False, "Question is not currently assigned to your team.", None
        if asgn["is_completed"]:
            return False, "Cannot revert a question that has already been completed.", None

        # 1. Try finding an unassigned question from bank
        cur.execute("""
            SELECT id FROM questions 
            WHERE is_active = 1 AND id NOT IN (
                SELECT question_id FROM question_assignments WHERE team_id = ?
            )
            LIMIT 1
        """, (team_id,))
        candidate = cur.fetchone()

        if candidate:
            new_qid = candidate["id"]
            # Mark old question abandoned
            cur.execute("""
                UPDATE question_assignments 
                SET is_abandoned = 1, is_unlocked = 0 
                WHERE team_id = ? AND question_id = ?
            """, (team_id, question_id))

            # Insert replacement with same question order
            cur.execute("""
                INSERT INTO question_assignments 
                (team_id, question_id, question_order, is_unlocked, is_completed, is_abandoned)
                VALUES (?, ?, ?, 1, 0, 0)
            """, (team_id, new_qid, asgn["question_order"]))
        else:
            # Fall back to swapping with a locked, unattempted question
            cur.execute("""
                SELECT question_id, question_order FROM question_assignments
                WHERE team_id = ? AND is_unlocked = 0 AND is_completed = 0 AND is_abandoned = 0
                ORDER BY question_order DESC
                LIMIT 1
            """, (team_id,))
            swap_target = cur.fetchone()
            if not swap_target:
                return False, "No alternative questions available.", None

            new_qid = swap_target["question_id"]
            # Mark old question abandoned
            cur.execute("""
                UPDATE question_assignments 
                SET is_abandoned = 1, is_unlocked = 0 
                WHERE team_id = ? AND question_id = ?
            """, (team_id, question_id))

            # Unlock swap target at current order
            cur.execute("""
                UPDATE question_assignments 
                SET is_unlocked = 1, question_order = ? 
                WHERE team_id = ? AND question_id = ?
            """, (asgn["question_order"], team_id, new_qid))

        # Mark powerup used
        cur.execute("""
            UPDATE powerups 
            SET is_used = 1, used_at = CURRENT_TIMESTAMP, target_question_id = ?
            WHERE team_id = ? AND powerup_type = 'GIT_REVERT'
        """, (question_id, team_id))

        conn.commit()
        return True, "Git Revert successful! Challenge replaced.", new_qid
    except Exception as e:
        conn.rollback()
        return False, str(e), None
    finally:
        conn.close()

def arm_double_commit(team_id, question_id):
    """Arms Double Commit (2x points or 0) for next submission on question."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT is_used, is_armed FROM powerups WHERE team_id = ? AND powerup_type = 'DOUBLE_COMMIT'", (team_id,))
        row = cur.fetchone()
        if not row:
            return False, "Power-up not found."
        if row["is_used"]:
            return False, "Double Commit has already been used by your team."

        cur.execute("""
            UPDATE powerups 
            SET is_armed = 1, target_question_id = ?
            WHERE team_id = ? AND powerup_type = 'DOUBLE_COMMIT'
        """, (question_id, team_id))
        conn.commit()
        return True, "Double Commit armed! Your next submission will score 2x points if accurate, or 0 if incorrect."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
