# Phase 1 local handoff

Updated and verified on 2 October 2026 in `/Users/sregi/Desktop/phase 1/EXITCODE_0`.

## Run and review

The local preview is available at http://127.0.0.1:5050. To restart it:

```sh
cd '/Users/sregi/Desktop/phase 1/EXITCODE_0'
./run_local.sh
```

The launcher uses `database/local_preview.db`. The existing `database/exit_code_0.db` was preserved; it is not the preview database. The original phase 1 files are backed up in `.local-backups/`. Nothing was committed, pushed, or deployed.

Organizer sign-in: `/admin/login`, username `admin`, local default password `exitcode0_admin_2026`. Register a participant team, then start the event from the organizer console to enter the arena. Set `ADMIN_PASSWORD` and a stable `SECRET_KEY` in the environment before the real event; without a stable secret, restarting the process invalidates sessions.

## What changed

- Rebuilt the public pages, registration, waiting room, arena, standings, results, quiz, and organizer console with a black-led, red-accented palette and the original compact technical event layout. The homepage editor program and geometry are preserved; its later authorized animation update is documented below.
- Integrated all seven unique supplied React components with locally bundled React, Motion, OGL, GSAP, and Hugeicons: PatternWaves, RubberSegment, ThoughtLine, BorderGlow, TechText, ElectricLogo, and DotGrid. Borders are clearly visible at rest and intensify near the pointer. Reduced-motion users receive static effects.
- Added code-line selection, local draft recovery, review markers, question navigation with browser history, server-synchronized timing, recoverable request errors, and fullscreen recovery.
- Added separate server-timed quiz scoring, final-results publication, organizer metrics, activity monitoring, submission review, and CSV exports.
- Hardened assignment validation, duplicate submission retries, transactional scoring, stale-session invalidation, and event transitions. Existing activity history migrates without duplication.

Implementation and API responsibilities are described in `README.md`. Core frontend changes are under `templates/`, `static/css/`, and `static/js/`; backend changes are in `app.py`, `database.py`, `event_manager.py`, `scoring.py`, and the new `quiz.py`.

## Verification completed

- **39 pytest tests passed**, including 20 concurrent logical teams with retry/idempotency checks, migration compatibility, quiz isolation, and reset identity.
- **10 critical acceptance scenarios passed** in `verify_critical_scenarios.py`.
- **16 browser journey groups passed** in `scripts/browser_smoke.cjs`: registration, lobby entry, arena, autosave, pause/resume, failed-network recovery, submission, history, fullscreen, leaderboard, organizer review/security, CSV, quiz, publication, reset, and no JavaScript errors.
- **React component checks passed** in `scripts/react_bits_smoke.cjs`: actual WebGL rendering/animation, BorderGlow pointer response, Motion tab dragging and keyboard/assistive activation, reduced motion, mobile layout, no-WebGL fallback, real submission trace, and no React/WebGL/JavaScript errors. `scripts/interaction_smoke.cjs` is a compatibility entry point for this check.
- Arena verified at 1366×768, 1440×900, 1920×1080, 768×1024, and 390×844. Public mobile pages checked at 390×844. Desktop arena fits the viewport; narrow layouts stack and allow vertical scrolling.
- Browser screenshots and the journey report are in ignored `artifacts/`. Browser tests ran against a separate `artifacts/browser-test.db`; Python tests use temporary databases.

Run Python checks with:

```sh
venv/bin/python -m pytest -q
venv/bin/python verify_critical_scenarios.py
```

Browser scripts require Playwright and Chrome. They deliberately require `EXITCODE_E2E=1` because they reset their target event. Only run them against an isolated test database/server (default port 5056), never the real competition server.

## Known boundaries

- The existing Team ID/name login model is retained. It is intended for a supervised lab and is not password-based participant authentication.
- The common 30-question Python/C/Java assignment is preserved. A language selector was not introduced because the existing bank has unequal difficulty distributions and no C++ track; adding one without equivalent question sets would change competition fairness.
- Focus/fullscreen activity is advisory evidence, not an automatic cheating verdict or penalty. Browser restrictions cannot prevent use of another device.
- Logical concurrency was tested locally. Physical lab machines, the college network, and real event load still need an organizer rehearsal.
- The preview uses Flask's development server for local review. This handoff does not claim production deployment or load certification.

## Final redesign checks

- All seven unique supplied effects are mounted and exercised. Repeated BorderGlow attachments are covered by the same component.
- Protected homepage demo markup and `landing.js` are byte-identical to the pre-redesign capture. Its desktop dimensions and interior screenshot pixels match; only antialiased outer corners blend into the new surrounding black background.
- Strong borders were checked for a visible 2px red edge at rest, including reduced motion. Registration, lobby, quiz, results and organizer surfaces use the same treatment.
- Full 16-group competition browser journey, 7-group original React smoke test, additional redesign/interaction checks, and 39 Python tests passed with no browser/React/WebGL errors.
- Responsive public layouts passed at 1440px, 768px, and 390px. The arena flow passed at 1366×768.
- Frame pacing in local headless Chrome: median 16.7ms across hero effects, electric logo, spring tabs/glow, and request trace; 95th percentile 16.7–16.8ms. Two isolated frames exceeded 50ms during control/trace startup. This is a local measurement, not a guarantee for every GPU or device.
- Original competition data was not reset by this redesign. Destructive browser tests used only `artifacts/browser-test.db`; read-only visual tests used the local preview.

The current preview remains at http://127.0.0.1:5050/?ui=black-red. No commit, push, or deployment was performed.

## Subsequent demo-only update

At the user's request, the formerly excluded homepage demo now matches the black/red theme. Its source program, existing markup and dimensions remain unchanged. React/Motion adds a moving line scan, fault emphasis, animated correction, test-progress bar and console transitions; the demo's BorderGlow and PatternWaves now use red.

The demo timer and animation controls pause together, suspend offscreen/when the tab is hidden, and use a static final state for reduced motion. The main title and event-information strip were compared against pre-update captures and remained pixel-identical. No other page, backend, registration flow or competition behavior was changed. Local checks are in `scripts/demo_motion_smoke.cjs`.
