# workouts — context

## What this is

Personal 5-day workout tracker, Flask + SQLite, live on the Pi at `:5016` (`workouts.service`). Simon logs sets/reps/weight per session and body weight separately; dashboard suggests the next day in the split.

## Session log

### 2026-09-11 (2)

- **Multi-leg, multi-mode cardio logging.** Simon's Day 4 cardio can now be a mixed workout (e.g. bike to the pool, swim, bike back) instead of one time/distance pair. Replaced the two `sessions.time_minutes`/`distance_miles` columns (kept, unused going forward, for legacy rows) with a new `cardio_legs` table: `session_id, leg_number, mode (bike/run/swim), time_seconds, distance_miles`. Up to 4 legs per session, fixed rows in the form (no JS add/remove — simplest thing that covers the stated 3-leg/2-mode case); a leg with no mode radio selected is skipped on save.
  - **Time entry**: replaced the `step=0.5` number input (only allowed increments of 30s) with a text field taking `mm:ss` (or `mm'ss"` stopwatch notation, or plain decimal minutes) via `parse_time_to_seconds()`/`format_seconds_to_mmss()`. Distance stays a decimal number input (already had `step=0.01`, that part wasn't actually broken).
  - `app.py`: `log_session` POST loops `mode_{i}`/`time_{i}`/`distance_{i}` for `i` in 1..4 into `cardio_legs`; GET prefills leg rows from the most recent cardio session's legs. `session_detail` shows a per-leg table (mode, time, distance, pace) with a totals row; falls back to the old single-row display + calorie/power estimate only when a session has no `cardio_legs` rows (pre-migration data).
  - **Calorie/power estimate scoped down**: `estimate_cardio_power()` is walk/run-specific (ACSM VO2 equations) and wasn't extended to bike/swim — multi-leg sessions just don't show an estimate. Legacy single-leg (run) sessions still get one.
  - `notebooks/analysis_lib.py`: `load_cardio()` now sums `cardio_legs` per session (`COALESCE`d against the legacy columns) so old and new sessions both plot correctly in the trajectory notebook.
  - Verified: parser round-trip (`11:20`, `11'20"`, plain minutes), full POST of a 3-leg bike/swim/bike session checked against the DB rows and totals, GET prefill from that session, legacy pre-migration session detail render, and `load_cardio()` aggregation across a mixed legacy+new DB — all via test-client/script against a throwaway DB, not the live one.
  - Not yet deployed — Simon to review locally, then `./push_pi.sh`.

### 2026-09-11 (1)

- **Free workout selection instead of forced next-day.** Simon wanted to pick any workout, not just the suggested next one. Replaced the single "Next Up" day (`next_day = (last.day % 5) + 1`) with `get_completed_days(conn)`: days logged since the most recent Monday, reset to empty (all available) once all 5 are logged — so a day is "available" (green border) until done this week, then "done" (red border, dimmed) until the whole week is cleared, at which point everything goes green again. Applied to both the dashboard's program grid (`index.html`) and the `/log` picker grid (`log.html`); CSS: `.day-card.available` (green), `.day-card.done` (red, opacity 0.6) replacing the old single `.next` class. No change to logging/history flow — `log_session` still accepts any day, dates still drive the dashboard charts.
  - Verified: test-client script inserted sessions into a throwaway DB covering empty week (all available), partial completion, all-5-done reset, and prior-week sessions not counting — all matched expected sets. `GET /` and `GET /log` both 200.
  - Not yet deployed — Simon to review locally first, then `./push_pi.sh`.

### 2026-07-17

- **Added cardio power estimate.** After Simon logged a real cardio session (20 min, 1.3 mi) and a body weight entry (216.4 lbs), asked to estimate power for cardio from the most recent body weight. Asked where it should live (notebook, live app, or both) — Simon said both. Implemented in both places, kept in sync manually (no shared import — notebooks intentionally never import `app.py`):
  - `notebooks/analysis_lib.py`: `add_cardio_power(cardio, bodyweight_lbs)` — ACSM level-ground walking/running VO2 equations (VO2 = 0.1*speed + 3.5 ml/kg/min below ~5 mph, 0.2*speed + 3.5 above), converted to kcal via ~5 kcal/L O2, then to watts over session duration. `plot_cardio_trajectory` extended with a 4th power panel when the column is present.
  - `app.py`: `estimate_cardio_power()` — same formula, computed at view time in `/session/<id>` for day-4 sessions, using the most recent `body_weight` row (falls back to `DEFAULT_BODYWEIGHT_LBS` if none logged).
  - `templates/session_detail.html`: cardio card now shows Est. Calories + Est. Power alongside Time/Distance/Pace, with a one-line caveat.
  - **Important caveat flagged in README, not just buried in a comment**: this is a *metabolic* power estimate (total energy expenditure rate from calories), not the *mechanical* work estimate the strength-day watts number uses. With real numbers (20 min, 1.3 mi, 216.4 lbs) it comes out to ~478 W — an order of magnitude higher than a typical strength-day watts figure (tens of W), because human metabolic-to-mechanical efficiency is only ~20-25%. The two numbers are not comparable and shouldn't be read as "cardio is more powerful than lifting."
  - Verified: notebook re-executed headlessly against the real pulled snapshot (post `pull_db.sh`) with the actual logged cardio + weight data, numbers cross-checked against a separate Flask test-client run of `app.py`'s `estimate_cardio_power` — both produced identical kcal/watts for the same inputs. Also checked the no-body-weight-logged fallback path and confirmed strength days show no est_kcal/power fields (no regression).
  - **Deployed** via `./push_pi.sh`.

### 2026-07-16

- **Simplified Day 4 (Cardio) logging.** The cardio day previously reused the strength-day form (3 sub-exercises — warm-up walk, intervals, cool-down walk — each with a weight/reps input per set), which never fit cardio and had nothing logged against it. Replaced with a single simple input: time (min) + distance (mi) per session. Changes:
  - `app.py`: `PROGRAM[4]["exercises"]` is now `[]`. Added `time_minutes`/`distance_miles` columns to `sessions` (idempotent `ALTER TABLE` migration in `init_db()`, safe to re-run). `log_session` special-cases `day == 4` on both GET (prefill from last cardio session) and POST (store on the `sessions` row, skip `logged_sets` entirely).
  - `templates/session.html` and `templates/session_detail.html`: day-4 branch renders/shows Time + Distance (+ computed pace in min/mi on the detail page) instead of the per-exercise weight/reps table.
  - `notebooks/day4_cardio.ipynb` + `notebooks/analysis_lib.py`: added `load_cardio()`/`plot_cardio_trajectory()` (reads `sessions.time_minutes`/`distance_miles` directly, plots time/distance/pace trajectories). The old weight/volume/power-estimate helpers in `analysis_lib.py` are now strength-day only (days 1, 2, 3, 5) — cardio never used them meaningfully.
  - Verified: Flask test client exercises GET/POST `/log/4` (prefill + save + detail-page rendering) and confirms strength days (`/log/1`) are unaffected; migration tested against a copy of the real `workouts.db`; all 3 touched notebooks (`day4_cardio`, `day1_upper_push`, `day2_lower`) re-executed headlessly with no errors, against a migrated copy of the snapshot DB (original snapshot file untouched — it'll pick up the new columns next time `pull_db.sh` runs post-deploy).
  - **Deployed** via `./push_pi.sh`. Verified live: `workouts.service` restarted clean, `GET /` and `GET /log/4` return 200, the cardio form renders Time/Distance inputs, and `sessions` on the live `workouts.db` picked up `time_minutes`/`distance_miles` via the automatic migration in `init_db()`. No lab_infra changes needed — same port, no new service.

### 2026-07-13

- **Day-picker fix (deployed).** The dashboard's "Start Workout" button used to jump straight to whatever `next_day` the app suggested, with no way to pick a different day from that primary CTA — even though the backend (`/log` route, `log.html`) already supported picking any day and had for a while. Changed the button in `templates/index.html` to link to `/log` (the picker), added a secondary "Quick Start Day N" button next to it for one-click accept of the suggestion. Deployed via `push_pi.sh`.
- **Clarified logging behavior (no code change).** Simon asked whether re-logging a day overwrites prior data — confirmed it doesn't. `log_session` POST always `INSERT`s a new `sessions` row + new `logged_sets` rows; the GET handler only pre-fills the form with the last session's numbers as a typing convenience (`value=` attribute in `session.html`). Every save is a new dated row.
- **Built `notebooks/` analysis toolkit.** Real data pulled from the Pi (`ssh simonhans@raspberrypi`, `sqlite3 /mnt/serverdrive/coding/workouts/workouts.db`) to build against reality: as of this date only Day 1 (Upper Push) has been logged, twice (2026-07-06, 2026-07-13), `body_weight` table is empty. Built:
  - `notebooks/pull_db.sh` — scp's a snapshot of the live DB down for local analysis; notebooks read only this local copy, never the live DB.
  - `notebooks/analysis_lib.py` — data loading (`load_data`, tidies weight/reps into a DataFrame, handles non-numeric reps like cardio's "5 min" via `pd.to_numeric(errors="coerce")`), volume calc, and the watts estimate (see README for the physics + assumptions).
  - 5 notebooks, one per program day, each thin — imports the lib, sets `DAY`, plots weight/volume/power trajectories.
  - **Bug found and fixed during verification:** the empty-data path in `load_data` was missing the `reps_numeric` column, and `add_power`'s `.apply(axis=1)` on an empty DataFrame throws `ValueError: Wrong number of items passed` under pandas 1.3.5 (Anaconda env here). Both fixed — days 2-5 (nothing logged yet) now render cleanly with "no sessions logged" placeholders instead of crashing. Verified by executing all 5 notebooks headlessly (`jupyter nbconvert --execute`) and checking for error outputs.
  - Local env: `pandas 1.3.5`, `matplotlib 3.1.3`, `numpy 1.21.6`, jupyter from `anaconda3`. No seaborn used (matplotlib + numpy only, per workspace rule).

## Data caveats

- No rep tempo or set timing is logged anywhere in the schema — the watts estimate in the notebooks is a physics approximation (mass x g x ROM x reps / assumed time), not measured power. See README for the exact assumptions and where to tune them.
- `body_weight` table is currently empty (Simon hasn't logged any weight entries), so the power estimate for bodyweight exercises (push-ups, pull-ups) is using the 175 lb fallback default, not a real number. Logging actual body weight via `/weight` would sharpen that estimate.
- Only Day 1 has any session data as of 2026-07-13. Days 2-5 notebooks are untested against real numbers (only against the empty-data path) — worth a sanity check once those days get logged.

## Status / next action

- App: day-picker fix is live on the Pi, working.
- Notebooks: built, verified to execute cleanly, not yet opened interactively by Simon. Next natural step is for Simon to actually look at the Day 1 notebook and react to whether the watts number feels meaningful, and adjust `ROM_METERS`/`SEC_PER_REP` in `analysis_lib.py` if not.
- No lab_infra changes needed — notebooks are local analysis tooling, not a deployed service, no new port.
