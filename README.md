# EXIT CODE 0 — Competitive Debugging Platform

> **Find the Bug. Fix the Code. Exit Clean.**

Official competition web application for the college-level **IEEE Week 2026** technical event, organized by the **IEEE Computer Society Student Branch Chapter**, Amrita Vishwa Vidyapeetham, Bengaluru.

**Event Date:** 7 October 2026 (Wednesday, 2:50 PM – 4:00 PM, 70 Minutes)  
**Target Audience:** B.Tech & M.Tech Students  
**Team Size:** 2–3 Members  
**Expected Participants:** 60  
**Format:** Single Round Only — Pure Debugging Challenge (NO seminar, NO presentation, NO audience voting).

---

## ⚡ Key Architectural Features

1. **Strict Server-Side Truth**:
   - Scores, question assignments, answer evaluation, power-up consumption, and timer state are managed exclusively in SQLite on the backend.
   - Answer keys are **never** delivered to the client or embedded in HTML/JS.
2. **Persistent 70-Minute Server Timer**:
   - Runs server-side in SQLite (`event_state` table) and survives browser reloads, page refreshes, and app restarts.
   - When time expires, submissions are automatically rejected and locked (HTTP 403).
3. **Anti-Copy Deterrents**:
   - Read-only code viewer with line numbers and syntax styling.
   - CSS & JS deterrents (`user-select: none`, right-click disabled, Ctrl+C / Ctrl+X disabled within code container, no copy button).
4. **30 Verified Debugging Questions**:
   - Preloaded in `data/questions.json` across Python, C, and Java with deterministic bugs, line numbers, expected outputs, causes, and verified corrections.
5. **Multi-Part Scoring Rubric with Partial Credit**:
   - Error Identification (Type 15% + Location 10%): 25%
   - Root-Cause Explanation: 25%
   - Expected Output Prediction: 20%
   - Verified Code Correction: 30%
   - Fuzzy text matching and line number normalization ensure fairness across phrasing variations.
6. **Tactical Power-Ups (1 Use Each per Team)**:
   - **🦆 RUBBER DUCK**: Reveals an architectural hint with a 10% base-point deduction.
   - **↺ GIT REVERT**: Abandons current question and swaps it for another active question.
   - **⚡ DOUBLE COMMIT**: 2× points if submission achieves $\ge 60\%$ accuracy; 0 points if incorrect.
7. **Live Real-Time Leaderboard with Tie-Breaker**:
   - Ranked by `Score DESC` $\rightarrow$ `Completed Questions DESC` $\rightarrow$ `Earlier Final Submission ASC`.
8. **Role-Separated Navigation Bars**:
   - **Participant Navbar**: `Home` (`/`), `Leadership Board` (`/leaderboard`), `Debugging` (`/arena`), `Score` (`/result`), `Team Name` (`EX0-001`), `Logout` (`/logout`).
   - **Admin Navbar** (active inside `/admin/*`): `Home` (`/admin/dashboard`), `Leadershipboard` (`/leaderboard`), `Debuggings` (`/admin/dashboard#controls`), `Debugging Questions` (`/admin/dashboard#questions`), `Logout` (`/admin/logout`), `← View Website`.

---

## 🛠️ Technology Stack

- **Frontend**: HTML5, Vanilla CSS3 (Custom Dark Theme with JetBrains Mono & Inter typography), Vanilla JavaScript (No React, Angular, Vue, Tailwind, or Bootstrap).
- **Backend**: Python 3.11+ with Flask.
- **Database**: SQLite3 via Python's built-in `sqlite3` (foreign keys, transaction safety, indexes).
- **Data/Config**: Static configuration in `data/config.json` and questions repository in `data/questions.json`.
- **Testing**: Automated test suite with `pytest`.

---

## 📂 Project Structure

```text
IEEE/
├── app.py                     # Main Flask application and API routes
├── config.py                  # Environment and event settings
├── database.py                # SQLite connection, registration, schema bootstrap
├── event_manager.py           # 70-min server countdown timer, state machine, lifecycle
├── scoring.py                 # Rubric evaluation, fuzzy matching, power-up logic
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation
│
├── database/
│   ├── schema.sql             # 9 normalized SQLite tables & indexes
│   └── exit_code_0.db         # Persistent SQLite tournament database
│
├── data/
│   ├── config.json            # Dynamic event configuration
│   └── questions.json         # 30 verified challenges across Python, C, and Java
│
├── templates/
│   ├── base.html              # Core layout with role-separated navbars
│   ├── index.html             # Landing page with telemetry and CTAs
│   ├── register.html          # Team registration (2-3 members) & login
│   ├── waiting.html           # Participant waiting room with auto-redirect
│   ├── arena.html             # Read-only code viewer, answer form, power-ups
│   ├── leaderboard.html       # Real-time scoreboard with tie-breaker
│   ├── result.html            # Final score receipt (Exit Status 0) & podium
│   ├── admin_login.html       # Secure admin authentication
│   ├── admin_dashboard.html   # Tournament lifecycle controls, roster, overrides
│   ├── 404.html               # Custom 404 error page
│   └── 500.html               # Custom 500 system error page
│
├── static/
│   ├── css/
│   │   └── style.css          # Developer-focused dark technical styling
│   └── js/
│       ├── main.js            # Global telemetry & notifications
│       ├── arena.js           # Anti-copy protection & submission handling
│       ├── timer.js           # Server-synchronized client timer
│       ├── leaderboard.js     # Live polling scoreboard
│       └── admin.js           # Event lifecycle controls & score overrides
│
└── tests/
    ├── test_database.py       # Initialization, registration, schema constraints
    ├── test_event.py          # Start, pause, resume, end, timer persistence, reset
    ├── test_scoring.py        # Submissions, rubric, power-ups, score calculation
    └── test_routes.py         # Routes, security boundaries, leaderboard, tie-break
```

---

## 🚀 Installation & Local Setup

### Windows

```powershell
# 1. Clone repository & navigate to directory
cd c:\Users\udata\OneDrive\Pictures\Desktop\IEEE

# 2. Create and activate Python virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install required dependencies
pip install -r requirements.txt

# 4. Run the application
python app.py
```

Open your browser at:
- **Participant Portal:** [http://127.0.0.1:5000](http://127.0.0.1:5000)
- **Admin Console:** [http://127.0.0.1:5000/admin/login](http://127.0.0.1:5000/admin/login)

---

## 🔑 Default Credentials & Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `ADMIN_USERNAME` | `admin` | Admin dashboard username |
| `ADMIN_PASSWORD` | `exitcode0_admin_2026` | Admin dashboard security password |
| `SECRET_KEY` | `exit_code_0_ieee_cs_amrita_2026_super_secret_key` | Flask session secret key |
| `PORT` | `5000` | Port for the local server |

Override any variable in your shell before launching:
```powershell
$env:ADMIN_PASSWORD="YourStrongPasswordHere"
python app.py
```

---

## 📋 Administrator Guide

### 1. Starting the Competition
1. Log in at `/admin/login` using your admin credentials.
2. In **Event Controls**, click **▶ START EVENT**.
3. The 70-minute tournament clock begins countdown. All teams waiting on `/waiting` will be automatically redirected to `/arena`.

### 2. Pausing & Resuming
- Click **⏸ PAUSE EVENT** to freeze the tournament timer. Remaining time is preserved in SQLite.
- Click **⏯ RESUME EVENT** to re-activate the timer from the exact remaining second.

### 3. Manual Score Overrides (Section 27)
1. In the **Submissions** stream on `/admin/dashboard`, locate any submission.
2. Click **Override Score**.
3. Input the new score (e.g. `20.0`) and enter the reason (e.g. *"Alternative valid explanation confirmed by judge"*).
4. Click **Save Override**. The submission score and team leaderboard score update immediately.

### 4. Exporting Tournament Data (Section 26)
- **Export Teams CSV**: Click `📥 Export Teams CSV` (or visit `/admin/export/teams.csv`) to download `teams_roster.csv`.
- **Export Results CSV**: Click `📥 Export Results CSV` (or visit `/admin/export/results.csv`) to download `final_leaderboard.csv`.

### 5. Safe Tournament Reset (Section 28)
To purge all teams, submissions, power-ups, and scores before a new round:
1. Click **⚠ RESET EVENT...** on the Admin Console.
2. Type **`RESET EVENT`** into the confirmation box.
3. Click **CONFIRM RESET**. The tournament clock resets back to 70 minutes and status returns to `WAITING`.

### 6. Modifying Event Duration
Edit `data/config.json`:
```json
{
  "event_name": "EXIT CODE 0",
  "duration_minutes": 70,
  "team_min_size": 2,
  "team_max_size": 3
}
```

---

## 🧪 Running Automated Tests

Run the full test suite using `pytest`:

```powershell
pytest
```

To run individual suites:
```powershell
pytest tests/test_database.py
pytest tests/test_event.py
pytest tests/test_scoring.py
pytest tests/test_routes.py
```

To run the 10 Critical Acceptance Scenarios script:
```powershell
python verify_critical_scenarios.py
```

---

## 🛡️ Security & Integrity Guarantees

- **No Client-Side Scoring**: JavaScript never decides scores, levels, or timers.
- **Answer Key Concealment**: Answer keys are stripped out before question data reaches the client.
- **CSRF & Session Security**: HTTP-only server sessions with isolated participant/admin state.
- **SQL Injection Prevention**: 100% of SQLite database operations utilize parameterized queries (`?`).
- **No Unsafe Execution**: Participant submissions are analyzed via deterministic string and token matching algorithms; participant code is **never** executed via Python `eval()` or `exec()`.

---

© 2026 IEEE Computer Society Student Branch Chapter, Amrita Vishwa Vidyapeetham, Bengaluru. All rights reserved.
