from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
import os
from datetime import date, datetime, timedelta

app = Flask(__name__)
DB = os.path.join(os.path.dirname(__file__), "workouts.db")

LB_TO_KG = 0.453592
MILE_TO_METER = 1609.34
KCAL_PER_LITER_O2 = 5.0  # rough approximation, RER ~1
WALK_RUN_SPEED_THRESHOLD_M_PER_MIN = 134.0  # ~5 mph; ACSM switches equations here
DEFAULT_BODYWEIGHT_LBS = 175.0
CARDIO_MODES = ["bike", "run", "swim"]
MAX_CARDIO_LEGS = 4

PROGRAM = {
    1: {
        "name": "Upper Push",
        "focus": "Chest · Shoulders · Triceps",
        "exercises": [
            {"name": "Dumbbell Bench Press",      "sets": 4, "reps": "8–10"},
            {"name": "Dumbbell Overhead Press",   "sets": 3, "reps": "8–10"},
            {"name": "Incline Dumbbell Press",    "sets": 3, "reps": "10–12"},
            {"name": "Lateral Raises",            "sets": 3, "reps": "12–15"},
            {"name": "Overhead Tricep Extension", "sets": 3, "reps": "12–15"},
            {"name": "Push-ups",                  "sets": 2, "reps": "AMRAP"},
        ],
    },
    2: {
        "name": "Lower",
        "focus": "Quads · Hamstrings · Glutes · Calves",
        "exercises": [
            {"name": "Goblet Squat",           "sets": 4, "reps": "10–12"},
            {"name": "Romanian Deadlift",       "sets": 4, "reps": "10–12"},
            {"name": "Dumbbell Lunges",         "sets": 3, "reps": "10 each"},
            {"name": "Step-ups",                "sets": 3, "reps": "12 each"},
            {"name": "Calf Raises",             "sets": 4, "reps": "15–20"},
            {"name": "Plank",                   "sets": 3, "reps": "45–60 sec"},
        ],
    },
    3: {
        "name": "Upper Pull + Core",
        "focus": "Back · Biceps · Rear Delts · Core",
        "exercises": [
            {"name": "Pull-ups",           "sets": 4, "reps": "AMRAP"},
            {"name": "Dumbbell Row",       "sets": 4, "reps": "10–12"},
            {"name": "Rear Delt Fly",      "sets": 3, "reps": "12–15"},
            {"name": "Hammer Curls",       "sets": 3, "reps": "12"},
            {"name": "Dead Bug",           "sets": 3, "reps": "10 each"},
            {"name": "Bicycle Crunches",   "sets": 3, "reps": "20"},
            {"name": "Russian Twists",     "sets": 3, "reps": "20"},
        ],
    },
    4: {
        "name": "Cardio",
        "focus": "Treadmill intervals or steady state",
        "exercises": [],
    },
    5: {
        "name": "Full Body + Mobility",
        "focus": "Compound movements · Stretch",
        "exercises": [
            {"name": "Dumbbell Deadlift",       "sets": 3, "reps": "10"},
            {"name": "Push-ups",                "sets": 3, "reps": "15"},
            {"name": "Pull-ups",                "sets": 3, "reps": "AMRAP"},
            {"name": "Dumbbell Shoulder Press", "sets": 3, "reps": "12"},
            {"name": "Dumbbell Curls",          "sets": 3, "reps": "12"},
            {"name": "Tricep Kickbacks",        "sets": 3, "reps": "12"},
            {"name": "Yoga / Stretching",       "sets": 1, "reps": "10–15 min"},
        ],
    },
}


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def estimate_cardio_power(time_minutes, distance_miles, bodyweight_lbs):
    """Estimated calories burned + average power (watts) for a cardio session.

    ACSM level-ground metabolic equations (VO2 as a linear function of speed,
    walking coefficient below ~5 mph and running above), converted to calories
    via ~5 kcal/L O2. A physiological estimate for spotting trends, not a
    lab-measured number — and not directly comparable to the strength-day watts
    estimate (that one's mechanical work; this is total metabolic rate).
    """
    if not time_minutes or not distance_miles or time_minutes <= 0 or distance_miles <= 0:
        return None, None
    speed_m_per_min = distance_miles * MILE_TO_METER / time_minutes
    coef = 0.2 if speed_m_per_min >= WALK_RUN_SPEED_THRESHOLD_M_PER_MIN else 0.1
    bodyweight_kg = bodyweight_lbs * LB_TO_KG
    vo2_ml_per_kg_min = coef * speed_m_per_min + 3.5
    kcal_per_min = vo2_ml_per_kg_min * bodyweight_kg / 1000 * KCAL_PER_LITER_O2
    est_kcal = kcal_per_min * time_minutes
    power_w = est_kcal * 4184 / (time_minutes * 60)
    return round(est_kcal, 1), round(power_w, 1)


def parse_time_to_seconds(s):
    """Accepts 'mm:ss', 'mm'ss"' (stopwatch notation), or plain decimal minutes."""
    s = s.strip().replace("'", ":").replace('"', "")
    if not s:
        return None
    if ":" in s:
        m, sec = s.split(":", 1)
        return int(round(float(m or 0) * 60 + float(sec or 0)))
    return int(round(float(s) * 60))


def format_seconds_to_mmss(total_seconds):
    if total_seconds is None:
        return ""
    m, sec = divmod(int(round(total_seconds)), 60)
    return f"{m}:{sec:02d}"


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            date    TEXT NOT NULL,
            day     INTEGER NOT NULL,
            rpe     INTEGER,
            notes   TEXT
        );

        CREATE TABLE IF NOT EXISTS logged_sets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL,
            exercise    TEXT NOT NULL,
            set_number  INTEGER NOT NULL,
            weight      REAL,
            reps        TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS body_weight (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            date    TEXT NOT NULL UNIQUE,
            weight  REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cardio_legs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            leg_number      INTEGER NOT NULL,
            mode            TEXT NOT NULL,
            time_seconds    INTEGER,
            distance_miles  REAL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
    """)

    cols = [r["name"] for r in conn.execute("PRAGMA table_info(sessions)")]
    if "time_minutes" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN time_minutes REAL")
    if "distance_miles" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN distance_miles REAL")

    conn.commit()
    conn.close()


def get_completed_days(conn):
    """Days already logged since the most recent Monday. Resets (empty set) once all 5 are done."""
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    rows = conn.execute(
        "SELECT DISTINCT day FROM sessions WHERE date >= ?", (week_start,)
    ).fetchall()
    completed = {r["day"] for r in rows}
    return completed if completed != set(PROGRAM.keys()) else set()


@app.route("/")
def index():
    conn = get_db()

    # Last 14 body weight entries for chart
    weights = conn.execute(
        "SELECT date, weight FROM body_weight ORDER BY date DESC LIMIT 14"
    ).fetchall()
    weights = list(reversed(weights))

    # Last 10 sessions
    sessions = conn.execute(
        "SELECT * FROM sessions ORDER BY date DESC LIMIT 10"
    ).fetchall()

    completed_days = get_completed_days(conn)

    # Per-session total volume (weight * reps for numeric reps)
    volume_rows = conn.execute("""
        SELECT s.date, s.day,
               SUM(CASE WHEN ls.weight IS NOT NULL AND CAST(ls.reps AS REAL) > 0
                        THEN ls.weight * CAST(ls.reps AS REAL) ELSE 0 END) AS volume
        FROM sessions s
        LEFT JOIN logged_sets ls ON ls.session_id = s.id
        GROUP BY s.id
        ORDER BY s.date ASC
        LIMIT 20
    """).fetchall()

    conn.close()
    return render_template(
        "index.html",
        program=PROGRAM,
        completed_days=completed_days,
        sessions=sessions,
        weights=weights,
        volume_rows=volume_rows,
    )


@app.route("/log", methods=["GET", "POST"])
def log_day():
    if request.method == "POST":
        day = int(request.form["day"])
        return redirect(url_for("log_session", day=day))
    conn = get_db()
    completed_days = get_completed_days(conn)
    conn.close()
    return render_template("log.html", program=PROGRAM, completed_days=completed_days)


@app.route("/log/<int:day>", methods=["GET", "POST"])
def log_session(day):
    if day not in PROGRAM:
        return redirect(url_for("log_day"))

    if request.method == "POST":
        rpe = request.form.get("rpe")
        notes = request.form.get("notes", "").strip()
        today = date.today().isoformat()

        conn = get_db()
        cur = conn.execute(
            "INSERT INTO sessions (date, day, rpe, notes) VALUES (?, ?, ?, ?)",
            (today, day, rpe or None, notes or None),
        )
        session_id = cur.lastrowid

        if day == 4:
            for i in range(1, MAX_CARDIO_LEGS + 1):
                mode = request.form.get(f"mode_{i}", "").strip()
                if mode not in CARDIO_MODES:
                    continue
                time_seconds = parse_time_to_seconds(request.form.get(f"time_{i}", ""))
                distance_str = request.form.get(f"distance_{i}", "").strip()
                distance_miles = float(distance_str) if distance_str else None
                if time_seconds is None and distance_miles is None:
                    continue
                conn.execute(
                    "INSERT INTO cardio_legs (session_id, leg_number, mode, time_seconds, distance_miles) VALUES (?, ?, ?, ?, ?)",
                    (session_id, i, mode, time_seconds, distance_miles),
                )
        else:
            exercises = PROGRAM[day]["exercises"]
            for ex in exercises:
                ex_name = ex["name"]
                for s in range(1, ex["sets"] + 1):
                    weight = request.form.get(f"weight_{ex_name}_{s}", "").strip()
                    reps = request.form.get(f"reps_{ex_name}_{s}", "").strip()
                    if weight or reps:
                        conn.execute(
                            "INSERT INTO logged_sets (session_id, exercise, set_number, weight, reps) VALUES (?, ?, ?, ?, ?)",
                            (session_id, ex_name, s, float(weight) if weight else None, reps or None),
                        )

        conn.commit()
        conn.close()
        return redirect(url_for("session_detail", session_id=session_id))

    if day == 4:
        conn = get_db()
        last_session = conn.execute(
            "SELECT id FROM sessions WHERE day = 4 ORDER BY date DESC LIMIT 1"
        ).fetchone()
        last_legs = []
        if last_session:
            last_legs = conn.execute(
                "SELECT * FROM cardio_legs WHERE session_id = ? ORDER BY leg_number",
                (last_session["id"],),
            ).fetchall()
        conn.close()
        return render_template(
            "session.html",
            day=day,
            workout=PROGRAM[day],
            last_legs=last_legs,
            cardio_modes=CARDIO_MODES,
            max_legs=MAX_CARDIO_LEGS,
            format_mmss=format_seconds_to_mmss,
        )

    # Pull last logged weights for each exercise as defaults
    conn = get_db()
    last_weights = {}
    for ex in PROGRAM[day]["exercises"]:
        rows = conn.execute("""
            SELECT ls.set_number, ls.weight, ls.reps
            FROM logged_sets ls
            JOIN sessions s ON s.id = ls.session_id
            WHERE ls.exercise = ? AND s.day = ?
            ORDER BY s.date DESC, ls.set_number ASC
            LIMIT ?
        """, (ex["name"], day, ex["sets"])).fetchall()
        if rows:
            last_weights[ex["name"]] = rows
    conn.close()

    return render_template(
        "session.html",
        day=day,
        workout=PROGRAM[day],
        last_weights=last_weights,
    )


@app.route("/session/<int:session_id>")
def session_detail(session_id):
    conn = get_db()
    session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        return redirect(url_for("index"))
    sets = conn.execute(
        "SELECT * FROM logged_sets WHERE session_id = ? ORDER BY exercise, set_number",
        (session_id,),
    ).fetchall()

    est_kcal = power_w = None
    legs = []
    if session["day"] == 4:
        legs = conn.execute(
            "SELECT * FROM cardio_legs WHERE session_id = ? ORDER BY leg_number", (session_id,)
        ).fetchall()
        if not legs:
            # legacy single-leg sessions predating cardio_legs
            bw_row = conn.execute("SELECT weight FROM body_weight ORDER BY date DESC LIMIT 1").fetchone()
            bodyweight_lbs = bw_row["weight"] if bw_row else DEFAULT_BODYWEIGHT_LBS
            est_kcal, power_w = estimate_cardio_power(
                session["time_minutes"], session["distance_miles"], bodyweight_lbs
            )

    conn.close()

    # Group sets by exercise
    grouped = {}
    for s in sets:
        grouped.setdefault(s["exercise"], []).append(s)

    total_time = sum(l["time_seconds"] for l in legs if l["time_seconds"]) or None
    total_distance = sum(l["distance_miles"] for l in legs if l["distance_miles"]) or None

    return render_template(
        "session_detail.html",
        session=session,
        grouped=grouped,
        program=PROGRAM,
        est_kcal=est_kcal,
        power_w=power_w,
        legs=legs,
        total_time=total_time,
        total_distance=total_distance,
        format_mmss=format_seconds_to_mmss,
    )


@app.route("/session/<int:session_id>/delete", methods=["POST"])
def delete_session(session_id):
    conn = get_db()
    conn.execute("DELETE FROM logged_sets WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("history"))


@app.route("/history")
def history():
    conn = get_db()
    sessions = conn.execute(
        "SELECT * FROM sessions ORDER BY date DESC"
    ).fetchall()
    conn.close()
    return render_template("history.html", sessions=sessions, program=PROGRAM)


@app.route("/exercise/<path:name>")
def exercise_history(name):
    conn = get_db()
    rows = conn.execute("""
        SELECT s.date, ls.set_number, ls.weight, ls.reps
        FROM logged_sets ls
        JOIN sessions s ON s.id = ls.session_id
        WHERE ls.exercise = ?
        ORDER BY s.date ASC, ls.set_number ASC
    """, (name,)).fetchall()
    conn.close()
    return render_template("exercise.html", name=name, rows=rows)


@app.route("/weight", methods=["GET", "POST"])
def weight():
    if request.method == "POST":
        w = request.form.get("weight", "").strip()
        d = request.form.get("date", date.today().isoformat()).strip()
        if w:
            conn = get_db()
            conn.execute(
                "INSERT INTO body_weight (date, weight) VALUES (?, ?) ON CONFLICT(date) DO UPDATE SET weight=excluded.weight",
                (d, float(w)),
            )
            conn.commit()
            conn.close()
        return redirect(url_for("weight"))

    conn = get_db()
    entries = conn.execute(
        "SELECT * FROM body_weight ORDER BY date DESC LIMIT 60"
    ).fetchall()
    conn.close()
    return render_template("weight.html", entries=entries, today=date.today().isoformat())


@app.route("/api/exercise/<path:name>")
def api_exercise(name):
    conn = get_db()
    rows = conn.execute("""
        SELECT s.date,
               MAX(ls.weight) as max_weight,
               SUM(CASE WHEN CAST(ls.reps AS REAL) > 0 THEN ls.weight * CAST(ls.reps AS REAL) ELSE 0 END) as volume
        FROM logged_sets ls
        JOIN sessions s ON s.id = ls.session_id
        WHERE ls.exercise = ?
        GROUP BY s.date
        ORDER BY s.date ASC
    """, (name,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5016, debug=False)
