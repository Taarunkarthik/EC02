import os
import io
import csv
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response

from config import Config
from database import (
    init_db, get_db_connection, register_team,
    log_admin_action, get_team_assigned_questions, get_client_question
)
from scoring import (
    process_submission, activate_rubber_duck, activate_git_revert,
    arm_double_commit
)
from event_manager import (
    get_event_state, start_event, pause_event, resume_event,
    end_event, reset_event_data
)

app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY

# Initialize database schema and seeds
init_db()

# --- Security Decorators & Context Processors ---

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def team_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("team_id"):
            return redirect(url_for("register", next=request.path))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_global_data():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM teams WHERE is_active = 1")
    teams_count = cur.fetchone()["count"]
    conn.close()
    
    ev_state = get_event_state()
    cfg = Config.load_event_config()
    return {
        "event_state": ev_state,
        "connected_teams": teams_count,
        "config": cfg
    }

# --- Error Handlers ---

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"Internal Server Error: {str(e)}")
    return render_template("500.html"), 500

# --- Public & Participant Views ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        action = request.form.get("action", "register")

        if action == "login":
            # Existing team sign in
            lookup = request.form.get("team_lookup", "").strip()
            if not lookup:
                return render_template("register.html", error="Please enter your Team ID or registered Team Name.")

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM teams 
                WHERE (UPPER(id) = UPPER(?) OR UPPER(name) = UPPER(?)) AND is_active = 1
            """, (lookup, lookup))
            team = cur.fetchone()
            conn.close()

            if not team:
                return render_template("register.html", error="Team not found. Please verify your Team ID or register your team.")

            session.clear()
            session["team_id"] = team["id"]
            session["team_name"] = team["name"]

            st = get_event_state()
            if st["event_status"] == "LIVE":
                return redirect(url_for("arena"))
            elif st["event_status"] == "COMPLETED":
                return redirect(url_for("result"))
            return redirect(url_for("waiting"))

        # Registration Flow: Exactly 2 to 3 members
        name = request.form.get("name", "").strip()
        member1 = request.form.get("member1", "").strip()
        member2 = request.form.get("member2", "").strip()
        member3 = request.form.get("member3", "").strip()
        email = request.form.get("email", "").strip()

        if not name:
            return render_template("register.html", error="Team Name is strictly required.")
        if not member1 or not member2:
            return render_template("register.html", error="Member 1 and Member 2 are required (teams must be 2 to 3 members).")

        team_id, err = register_team(name, member1, member2, member3, email)
        if err:
            return render_template("register.html", error=err)

        session.clear()
        session["team_id"] = team_id
        session["team_name"] = name
        session["just_registered"] = True  # one-shot: waiting room shows "TEAM INITIALIZED"

        st = get_event_state()
        if st["event_status"] == "LIVE":
            return redirect(url_for("arena"))
        return redirect(url_for("waiting"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    return redirect(url_for("register"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/waiting")
@app.route("/waiting-room")
@team_required
def waiting():
    team_id = session.get("team_id")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
    team = cur.fetchone()
    
    cur.execute("SELECT * FROM participants WHERE team_id = ? ORDER BY id ASC", (team_id,))
    members = cur.fetchall()

    cur.execute("SELECT COUNT(*) as count FROM teams WHERE is_active = 1")
    teams_count = cur.fetchone()["count"]
    conn.close()

    st = get_event_state()
    if st["event_status"] == "LIVE":
        return redirect(url_for("arena"))
    elif st["event_status"] == "COMPLETED":
        return redirect(url_for("result"))

    just_registered = session.pop("just_registered", False)
    return render_template("waiting.html", team=team, members=members, teams_count=teams_count,
                           just_registered=just_registered)

@app.route("/arena")
@app.route("/debug-arena")
@team_required
def arena():
    team_id = session.get("team_id")
    st = get_event_state()

    # Route gate: if event is waiting or completed
    if st["event_status"] == "WAITING":
        return redirect(url_for("waiting"))
    elif st["event_status"] == "COMPLETED":
        return redirect(url_for("result"))

    conn = get_db_connection()
    cur = conn.cursor()

    # Team & Score details
    cur.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
    team = cur.fetchone()

    cur.execute("SELECT * FROM scores WHERE team_id = ?", (team_id,))
    score = cur.fetchone()

    # Team assigned questions progression
    cur.execute("""
        SELECT q.id, q.language, q.title, q.difficulty, q.points,
               qa.question_order, qa.is_unlocked, qa.is_completed, qa.is_abandoned
        FROM question_assignments qa
        JOIN questions q ON qa.question_id = q.id
        WHERE qa.team_id = ? AND qa.is_abandoned = 0
        ORDER BY qa.question_order ASC
    """, (team_id,))
    assigned_questions = cur.fetchall()

    # Select active question: by ?q=Qxx or first unlocked uncompleted
    req_qid = request.args.get("q")
    current_question = None

    if req_qid:
        for q in assigned_questions:
            if q["id"] == req_qid and q["is_unlocked"]:
                current_question = q
                break

    if not current_question:
        # Default to first unlocked uncompleted, or first unlocked
        uncompleted = [q for q in assigned_questions if q["is_unlocked"] and not q["is_completed"]]
        if uncompleted:
            current_question = uncompleted[0]
        else:
            unlocked = [q for q in assigned_questions if q["is_unlocked"]]
            current_question = unlocked[0] if unlocked else (assigned_questions[0] if assigned_questions else None)

    # Fetch sanitized client code and details for current question
    client_q = None
    if current_question:
        cur.execute("SELECT id, language, title, difficulty, points, code FROM questions WHERE id = ?", (current_question["id"],))
        client_q = cur.fetchone()

    # Fetch power-ups status
    cur.execute("SELECT * FROM powerups WHERE team_id = ?", (team_id,))
    powerups = {p["powerup_type"]: dict(p) for p in cur.fetchall()}

    conn.close()

    # Navigator metadata (id/order/difficulty/points/state only — never answer data)
    nav_meta = [{"id": q["id"], "order": q["question_order"], "language": q["language"],
                 "difficulty": q["difficulty"], "points": q["points"],
                 "unlocked": bool(q["is_unlocked"]), "completed": bool(q["is_completed"])}
                for q in assigned_questions]

    return render_template(
        "arena.html",
        nav_meta=nav_meta,
        team=team,
        score=score,
        assigned_questions=assigned_questions,
        current_question=current_question,
        client_q=client_q,
        powerups=powerups
    )

@app.route("/leaderboard")
def leaderboard():
    return render_template("leaderboard.html")

@app.route("/result")
@app.route("/final-result")
def result():
    team_id = session.get("team_id")
    conn = get_db_connection()
    cur = conn.cursor()

    team = None
    score = None
    if team_id:
        cur.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
        team = cur.fetchone()
        cur.execute("SELECT * FROM scores WHERE team_id = ?", (team_id,))
        score = cur.fetchone()

    # Calculate Top 3 Winners (Ranked by Score DESC, Completed Count DESC, Time ASC)
    cur.execute("""
        SELECT 
            t.id, t.name,
            COALESCE(s.score, 0) as total_score,
            COALESCE(s.completed_count, 0) as completed_count,
            MIN(s.last_submission_time) as finish_time
        FROM teams t
        LEFT JOIN scores s ON t.id = s.team_id
        WHERE t.is_active = 1
        GROUP BY t.id
        ORDER BY total_score DESC, completed_count DESC, finish_time ASC
        LIMIT 3
    """)
    winners = cur.fetchall()

    conn.close()
    return render_template("result.html", team=team, score=score, winners=winners)

# --- JSON API Endpoints ---

@app.route("/api/event-status")
def api_event_status():
    st = get_event_state()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as count FROM teams WHERE is_active = 1")
    teams_count = cur.fetchone()["count"]
    conn.close()
    
    st["connected_teams"] = teams_count
    return jsonify(st)

@app.route("/api/question/<qid>")
@team_required
def api_get_question(qid):
    team_id = session.get("team_id")
    q = get_client_question(team_id, qid)
    if not q:
        return jsonify({"success": False, "error": "Question not found or not unlocked for your team."}), 404
    return jsonify({"success": True, "question": q})

@app.route("/api/submit-bug-fix", methods=["POST"])
@team_required
def api_submit_bug_fix():
    team_id = session.get("team_id")
    st = get_event_state()

    # Reject submission if event is not live
    if st["event_status"] != "LIVE" or st["remaining_seconds"] <= 0:
        return jsonify({
            "success": False, 
            "error": "The competition is not currently active. Submissions are closed."
        }), 403

    data = request.get_json() or {}
    question_id = data.get("question_id")
    if not question_id:
        return jsonify({"success": False, "error": "Question ID required."}), 400

    result, err = process_submission(team_id, question_id, data)
    if err:
        return jsonify({"success": False, "error": err}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT score, completed_count FROM scores WHERE team_id = ?", (team_id,))
    sc = cur.fetchone()
    conn.close()

    return jsonify({
        "success": True,
        "result": result,
        "new_score": round(sc["score"], 1) if sc else 0.0,
        "completed_count": sc["completed_count"] if sc else 0
    })

@app.route("/api/powerup/rubber-duck", methods=["POST"])
@team_required
def api_powerup_rubber_duck():
    team_id = session.get("team_id")
    st = get_event_state()
    if st["event_status"] != "LIVE" or st["remaining_seconds"] <= 0:
        return jsonify({"success": False, "error": "Competition is not active."}), 403

    data = request.get_json() or {}
    question_id = data.get("question_id")
    if not question_id:
        return jsonify({"success": False, "error": "Question ID required."}), 400

    success, msg, hint = activate_rubber_duck(team_id, question_id)
    if not success:
        return jsonify({"success": False, "error": msg}), 400

    return jsonify({"success": True, "message": msg, "hint": hint})

@app.route("/api/powerup/git-revert", methods=["POST"])
@team_required
def api_powerup_git_revert():
    team_id = session.get("team_id")
    st = get_event_state()
    if st["event_status"] != "LIVE" or st["remaining_seconds"] <= 0:
        return jsonify({"success": False, "error": "Competition is not active."}), 403

    data = request.get_json() or {}
    question_id = data.get("question_id")
    if not question_id:
        return jsonify({"success": False, "error": "Question ID required."}), 400

    success, msg, new_qid = activate_git_revert(team_id, question_id)
    if not success:
        return jsonify({"success": False, "error": msg}), 400

    return jsonify({"success": True, "message": msg, "new_question_id": new_qid})

@app.route("/api/powerup/double-commit", methods=["POST"])
@team_required
def api_powerup_double_commit():
    team_id = session.get("team_id")
    st = get_event_state()
    if st["event_status"] != "LIVE" or st["remaining_seconds"] <= 0:
        return jsonify({"success": False, "error": "Competition is not active."}), 403

    data = request.get_json() or {}
    question_id = data.get("question_id")
    if not question_id:
        return jsonify({"success": False, "error": "Question ID required."}), 400

    success, msg = arm_double_commit(team_id, question_id)
    if not success:
        return jsonify({"success": False, "error": msg}), 400

    return jsonify({"success": True, "message": msg})

@app.route("/api/team-name-available")
def api_team_name_available():
    """Inline validation helper for the registration form (team names are public on the leaderboard)."""
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"available": False, "reason": "empty"})
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM teams WHERE UPPER(name) = UPPER(?)", (name,))
    taken = cur.fetchone() is not None
    conn.close()
    return jsonify({"available": not taken})

ACTIVITY_TYPES = {"focus_lost", "focus_regained", "fullscreen_enter", "fullscreen_exit", "tab_hidden", "tab_visible"}

@app.route("/api/activity", methods=["POST"])
@team_required
def api_activity():
    """Organizer signal only. Team ID comes from the session, never the request body."""
    team_id = session.get("team_id")
    etype = (request.get_json(silent=True) or {}).get("type")
    if etype not in ACTIVITY_TYPES:
        return jsonify({"success": False}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    # throttle: ignore identical events from the same team within 1 second
    cur.execute("""SELECT 1 FROM activity_events WHERE team_id = ? AND event_type = ?
                   AND created_at >= datetime('now', '-1 seconds')""", (team_id, etype))
    if not cur.fetchone():
        cur.execute("INSERT INTO activity_events (team_id, event_type) VALUES (?, ?)", (team_id, etype))
        conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/leaderboard-data")
def api_leaderboard_data():
    conn = get_db_connection()
    cur = conn.cursor()

    # Query with tie-breaker:
    # 1. Higher total score
    # 2. Higher number of completed questions
    # 3. Earlier final qualifying submission time
    cur.execute("""
        SELECT 
            t.id, 
            t.name, 
            COALESCE(s.score, 0) as score,
            COALESCE(s.completed_count, 0) as completed_count,
            MIN(s.last_submission_time) as finish_time,
            t.is_active
        FROM teams t
        LEFT JOIN scores s ON t.id = s.team_id
        WHERE t.is_active = 1
        GROUP BY t.id
        ORDER BY score DESC, completed_count DESC, finish_time ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    st = get_event_state()

    return jsonify({
        "leaderboard": rows,
        "current_team_id": session.get("team_id"),
        "event_status": st["event_status"]
    })

# --- Admin Portal Routes & Actions ---

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pwd = request.form.get("password", "").strip()

        if user == Config.ADMIN_USERNAME and pwd == Config.ADMIN_PASSWORD:
            session.clear()
            session["is_admin"] = True
            log_admin_action("LOGIN", f"Admin logged in from {request.remote_addr}")
            return redirect(url_for("admin_dashboard"))

        return render_template("admin_login.html", error="Invalid admin security credentials.")

    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as c FROM teams")
    team_count = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM submissions")
    submission_count = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM questions WHERE is_active = 1")
    question_count = cur.fetchone()["c"]

    # All registered teams with member list & scores
    cur.execute("""
        SELECT t.id, t.name, t.created_at, t.is_active,
               COALESCE(s.score, 0) as score,
               COALESCE(s.completed_count, 0) as completed_count,
               (
                 SELECT GROUP_CONCAT(name, ', ') 
                 FROM participants 
                 WHERE team_id = t.id
               ) as members
        FROM teams t
        LEFT JOIN scores s ON t.id = s.team_id
        ORDER BY t.created_at DESC
    """)
    teams = cur.fetchall()

    # All 30 questions with answer keys
    cur.execute("SELECT * FROM questions ORDER BY id ASC")
    questions = cur.fetchall()

    # Recent submissions stream
    cur.execute("""
        SELECT s.*, t.name as team_name, q.title as question_title
        FROM submissions s
        JOIN teams t ON s.team_id = t.id
        JOIN questions q ON s.question_id = q.id
        ORDER BY s.id DESC
        LIMIT 50
    """)
    submissions = cur.fetchall()

    conn.close()
    return render_template(
        "admin_dashboard.html",
        team_count=team_count,
        submission_count=submission_count,
        question_count=question_count,
        teams=teams,
        questions=questions,
        submissions=submissions
    )

@app.route("/api/admin/event-action", methods=["POST"])
@admin_required
def api_admin_event_action():
    action = (request.get_json() or {}).get("action")
    if action == "start":
        ok, msg = start_event()
    elif action == "pause":
        ok, msg = pause_event()
    elif action == "resume":
        ok, msg = resume_event()
    elif action == "end" or action == "end_event":
        ok, msg = end_event()
    else:
        return jsonify({"success": False, "error": f"Unknown event action: {action}"}), 400

    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})

@app.route("/api/admin/override-score", methods=["POST"])
@admin_required
def api_admin_override_score():
    data = request.get_json() or {}
    sub_id = data.get("submission_id")
    new_score = data.get("new_score")
    reason = data.get("reason", "Admin manual scoring override")

    if sub_id is None or new_score is None:
        return jsonify({"success": False, "error": "Submission ID and new score are required."}), 400

    try:
        new_sc = float(new_score)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid score value."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT team_id FROM submissions WHERE id = ?", (sub_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "Submission not found."}), 404

    team_id = row["team_id"]

    cur.execute("""
        UPDATE submissions 
        SET total_score = ?, override_reason = ? 
        WHERE id = ?
    """, (new_sc, reason, sub_id))

    # Recalculate team total score
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
        SET score = ?, completed_count = ?, last_updated = CURRENT_TIMESTAMP 
        WHERE team_id = ?
    """, (total_score, comp_count, team_id))

    conn.commit()
    conn.close()
    log_admin_action("OVERRIDE_SCORE", f"Set submission #{sub_id} score to {new_sc}. Reason: {reason}")
    return jsonify({"success": True, "message": f"Submission #{sub_id} updated to {new_sc} points."})

@app.route("/api/admin/toggle-team", methods=["POST"])
@admin_required
def api_admin_toggle_team():
    team_id = (request.get_json() or {}).get("team_id")
    if not team_id:
        return jsonify({"success": False, "error": "Team ID required."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE teams SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (team_id,))
    conn.commit()
    conn.close()
    log_admin_action("TOGGLE_TEAM", f"Toggled active state for team {team_id}.")
    return jsonify({"success": True, "message": f"Team {team_id} status toggled."})

@app.route("/api/admin/toggle-question", methods=["POST"])
@admin_required
def api_admin_toggle_question():
    question_id = (request.get_json() or {}).get("question_id")
    if not question_id:
        return jsonify({"success": False, "error": "Question ID required."}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE questions SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()
    log_admin_action("TOGGLE_QUESTION", f"Toggled active state for question {question_id}.")
    return jsonify({"success": True, "message": f"Question {question_id} status toggled."})

@app.route("/api/admin/reset-event", methods=["POST"])
@admin_required
def api_admin_reset_event():
    conf = (request.get_json() or {}).get("confirmation", "")
    ok, msg = reset_event_data(conf)
    if not ok:
        return jsonify({"success": False, "error": msg}), 400
    return jsonify({"success": True, "message": msg})

# --- CSV Export Endpoints ---

@app.route("/admin/export/teams.csv")
@admin_required
def export_teams_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.name, t.created_at,
               (SELECT GROUP_CONCAT(name, ' / ') FROM participants WHERE team_id = t.id) as roster,
               t.is_active
        FROM teams t ORDER BY t.id ASC
    """)
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Team ID", "Team Name", "Team Members Roster", "Registration Time", "Status"])
    for r in rows:
        writer.writerow([r["id"], r["name"], r["roster"], r["created_at"], "ACTIVE" if r["is_active"] else "DISABLED"])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=teams_roster.csv"}
    )

@app.route("/admin/export/results.csv")
@admin_required
def export_results_csv():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            t.id, t.name,
            (SELECT GROUP_CONCAT(name, ' / ') FROM participants WHERE team_id = t.id) as roster,
            COALESCE(s.completed_count, 0) as completed_count,
            COALESCE(s.score, 0) as score,
            MIN(s.last_submission_time) as finish_time
        FROM teams t
        LEFT JOIN scores s ON t.id = s.team_id
        WHERE t.is_active = 1
        GROUP BY t.id
        ORDER BY score DESC, completed_count DESC, finish_time ASC
    """)
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Rank", "Team ID", "Team Name", "Roster", "Questions Completed", "Final Score", "Last Submission"])
    for idx, r in enumerate(rows, 1):
        writer.writerow([
            idx, r["id"], r["name"], r["roster"],
            r["completed_count"], f"{r['score']:.1f}", r["finish_time"] or "N/A"
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=final_leaderboard.csv"}
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n==========================================")
    print(f" EXIT CODE 0 -- IEEE COMPUTER SOCIETY")
    print(f" 70-Minute Competitive Debugging Arena")
    print(f" Access URL: http://127.0.0.1:{port}")
    print(f" Admin URL:  http://127.0.0.1:{port}/admin/login")
    print(f"==========================================\n")
    app.run(host="127.0.0.1", port=port, debug=True)
