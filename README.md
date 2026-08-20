# workouts

Flask + SQLite workout tracker. 5-day upper/lower split, logs sets/reps/weight, RPE, and body weight. Runs on the Pi at port 5016.

## App

- `app.py` — routes, program definition (`PROGRAM` dict, days 1-5), SQLite schema (`sessions`, `logged_sets`, `body_weight`).
- `templates/` — dashboard (`index.html`), day picker (`log.html`), per-day logging form (`session.html`), history, per-exercise view, body weight log.
- Dashboard's "Start Workout" opens the day picker (any of the 5 days); "Quick Start Day N" jumps straight into the suggested next day.
- Day 4 (Cardio) is logged differently from the other days: just time (min) + distance (mi), no sets/reps/weight. Stored directly on the `sessions` row (`time_minutes`, `distance_miles` columns), not in `logged_sets`.
- Cardio session detail page also shows an estimated calories/power (watts) figure, computed at view time from time + distance + the most recent `/weight` entry (`estimate_cardio_power` in `app.py`). It's a metabolic estimate (ACSM walk/run VO2 equations), not mechanical work — **not directly comparable** to the strength-day watts estimate in the notebooks, which measures mechanical work instead.
- Deploy: `./push_pi.sh` (rsyncs to the Pi, restarts `workouts.service`). Never edit files on the Pi directly.

## Notebooks

`notebooks/` — one Jupyter notebook per program day (`day1_upper_push.ipynb` ... `day5_full_body_mobility.ipynb`) for looking at progress over time.

- Days 1, 2, 3, 5 (strength days): top-set weight trajectory, total volume per session, and an estimated-power (watts) trend.
- Day 4 (Cardio): time, distance, pace, and an estimated-power trajectory, read straight from the `sessions` table — no volume estimate (that's strength-day only, since cardio doesn't log sets/reps/weight).
- `notebooks/pull_db.sh` — scp's a fresh read-only snapshot of the live DB from the Pi into `notebooks/data/workouts_snapshot.db`. Run this before opening a notebook to see current data; the notebooks never touch the live DB or the app.
- `notebooks/analysis_lib.py` — shared loading/plotting code all 5 notebooks import. `load_cardio` / `add_cardio_power` / `plot_cardio_trajectory` are cardio-specific; the rest (`load_data`, `add_volume`, `add_power`, etc.) are strength-day only.
- **Cardio power estimate** (`add_cardio_power` in `analysis_lib.py`, mirrored by `estimate_cardio_power` in `app.py` for the live session detail page): ACSM level-ground walking/running VO2 equations (walking coefficient below ~5 mph, running above), using the most recent `/weight` entry as body mass, converted to calories via ~5 kcal/L O2 then to watts over session duration. This is a **metabolic** estimate (total energy expenditure rate) — not the same kind of number as the strength-day **mechanical** watts estimate below, so don't compare them directly. The two implementations (notebook + app) are kept in sync manually since the notebooks intentionally never import from `app.py`.
- **Watts are an estimate, not a measurement.** The app doesn't log time on strength days — no rep tempo, no rest time. Power is derived from `work = mass * g * range_of_motion * reps`, divided by an assumed 3 sec/rep (`SEC_PER_REP` in `analysis_lib.py`). Range-of-motion per exercise (`ROM_METERS`) and bodyweight-exercise load fractions (`BODYWEIGHT_FRACTION`, e.g. push-ups ~64% of bodyweight) are rough visual estimates, editable in the same file. Treat the number as a relative trend (is this session's average watts higher than last time's?), not a lab-accurate figure.
- Bodyweight used in the estimate comes from the most recent `/weight` log entry; falls back to 175 lbs (`DEFAULT_BODYWEIGHT_LBS`) if nothing's logged yet.
