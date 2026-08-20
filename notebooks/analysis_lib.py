"""
Shared loading/plotting/power-estimate helpers for the per-day workout notebooks.

Power ("watts") is NOT measured — the app only logs weight and reps, not time.
It's derived from a physics estimate: work = mass * g * range_of_motion * reps,
divided by an assumed time per rep. Treat it as a relative trend indicator
(are you moving more work per second than last time?), not a lab-accurate number.
Tune ROM_METERS / SEC_PER_REP / BODYWEIGHT_LBS below to match reality better.
"""
import os
import sqlite3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

LB_TO_KG = 0.453592
G = 9.81  # m/s^2

# Estimated concentric+eccentric range of motion per exercise, in meters.
# Rough visual estimates, not measured — adjust freely.
ROM_METERS = {
    "Dumbbell Bench Press": 0.45,
    "Dumbbell Overhead Press": 0.45,
    "Incline Dumbbell Press": 0.40,
    "Lateral Raises": 0.55,
    "Overhead Tricep Extension": 0.35,
    "Goblet Squat": 0.50,
    "Romanian Deadlift": 0.35,
    "Dumbbell Lunges": 0.45,
    "Step-ups": 0.40,
    "Calf Raises": 0.10,
    "Dumbbell Row": 0.35,
    "Rear Delt Fly": 0.40,
    "Hammer Curls": 0.35,
    "Dumbbell Deadlift": 0.35,
    "Dumbbell Shoulder Press": 0.45,
    "Dumbbell Curls": 0.35,
    "Tricep Kickbacks": 0.30,
}

# Bodyweight exercises: fraction of bodyweight actually lifted (rough biomechanics estimates),
# used as mass in place of a logged dumbbell weight.
BODYWEIGHT_FRACTION = {
    "Push-ups": 0.64,
    "Pull-ups": 1.00,
}
ROM_METERS["Push-ups"] = 0.30
ROM_METERS["Pull-ups"] = 0.45

# Assumed seconds per rep (concentric + eccentric). Tune to your actual tempo.
SEC_PER_REP = 3.0

# Fallback bodyweight (lbs) if nothing's logged yet on the /weight page.
DEFAULT_BODYWEIGHT_LBS = 175.0


def load_data(day, db_path=None):
    """Returns (sessions_df, sets_df) for a given program day, joined and tidy."""
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "data", "workouts_snapshot.db")
    conn = sqlite3.connect(db_path)
    sessions = pd.read_sql_query(
        "SELECT id AS session_id, date, day, rpe, notes FROM sessions WHERE day = ? ORDER BY date",
        conn, params=(day,),
    )
    sessions["date"] = pd.to_datetime(sessions["date"])

    if sessions.empty:
        conn.close()
        return sessions, pd.DataFrame(columns=[
            "session_id", "date", "exercise", "set_number", "weight", "reps", "reps_numeric"
        ])

    sets = pd.read_sql_query(
        """
        SELECT ls.session_id, s.date, ls.exercise, ls.set_number, ls.weight, ls.reps
        FROM logged_sets ls
        JOIN sessions s ON s.id = ls.session_id
        WHERE s.day = ?
        ORDER BY s.date, ls.exercise, ls.set_number
        """,
        conn, params=(day,),
    )
    conn.close()
    sets["date"] = pd.to_datetime(sets["date"])
    sets["reps_numeric"] = pd.to_numeric(sets["reps"], errors="coerce")
    return sessions, sets


MILE_TO_METER = 1609.34
KCAL_PER_LITER_O2 = 5.0  # rough approximation, RER ~1
WALK_RUN_SPEED_THRESHOLD_M_PER_MIN = 134.0  # ~5 mph; ACSM switches equations here


def add_cardio_power(cardio, bodyweight_lbs=None):
    """Adds estimated calories burned and average power (watts) per cardio session.

    Uses the ACSM level-ground metabolic equations (VO2 in ml/kg/min as a linear
    function of speed, walking below ~5 mph and running above), converted to
    calories via ~5 kcal/L O2, then to watts over the session duration. Same
    caveat as the strength-day watts estimate: a physiological approximation for
    spotting trends session over session, not a lab-measured number.
    """
    cardio = cardio.copy()
    if bodyweight_lbs is None:
        bodyweight_lbs = DEFAULT_BODYWEIGHT_LBS
    bodyweight_kg = bodyweight_lbs * LB_TO_KG

    def _row(row):
        t, d = row["time_minutes"], row["distance_miles"]
        if pd.isna(t) or pd.isna(d) or t <= 0 or d <= 0:
            return pd.Series({"est_kcal": np.nan, "power_w": np.nan})
        speed_m_per_min = d * MILE_TO_METER / t
        coef = 0.2 if speed_m_per_min >= WALK_RUN_SPEED_THRESHOLD_M_PER_MIN else 0.1
        vo2_ml_per_kg_min = coef * speed_m_per_min + 3.5
        kcal_per_min = vo2_ml_per_kg_min * bodyweight_kg / 1000 * KCAL_PER_LITER_O2
        est_kcal = kcal_per_min * t
        power_w = est_kcal * 4184 / (t * 60)
        return pd.Series({"est_kcal": est_kcal, "power_w": power_w})

    cardio[["est_kcal", "power_w"]] = cardio.apply(_row, axis=1)
    return cardio


def load_cardio(db_path=None):
    """Returns a tidy DataFrame of cardio (Day 4) sessions: date, time_minutes, distance_miles, pace_min_per_mile."""
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "data", "workouts_snapshot.db")
    conn = sqlite3.connect(db_path)
    sessions = pd.read_sql_query(
        "SELECT date, rpe, notes, time_minutes, distance_miles FROM sessions WHERE day = 4 ORDER BY date",
        conn,
    )
    conn.close()
    sessions["date"] = pd.to_datetime(sessions["date"])
    sessions["pace_min_per_mile"] = np.where(
        sessions["distance_miles"] > 0,
        sessions["time_minutes"] / sessions["distance_miles"],
        np.nan,
    )
    return sessions


def plot_cardio_trajectory(cardio):
    """Time, distance, pace (and power, if computed via add_cardio_power) trajectories for cardio sessions."""
    has_power = "power_w" in cardio.columns
    n = 4 if has_power else 3
    fig, axes = plt.subplots(n, 1, figsize=(9, 13 if has_power else 10), sharex=True)

    axes[0].plot(cardio["date"], cardio["time_minutes"], marker="o", color="#4f8ef7")
    axes[0].set_title("Time per session")
    axes[0].set_ylabel("Minutes")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(cardio["date"], cardio["distance_miles"], marker="o", color="#7c5cbf")
    axes[1].set_title("Distance per session")
    axes[1].set_ylabel("Miles")
    axes[1].grid(True, alpha=0.3)

    pace = cardio.dropna(subset=["pace_min_per_mile"])
    if pace.empty:
        axes[2].text(0.5, 0.5, "No pace data yet (need both time and distance)",
                      ha="center", va="center", transform=axes[2].transAxes)
    else:
        axes[2].plot(pace["date"], pace["pace_min_per_mile"], marker="o", color="#f78c4f")
    axes[2].set_title("Pace per session")
    axes[2].set_ylabel("Min / mile")
    axes[2].grid(True, alpha=0.3)

    if has_power:
        power = cardio.dropna(subset=["power_w"])
        if power.empty:
            axes[3].text(0.5, 0.5, "No power estimate available yet",
                          ha="center", va="center", transform=axes[3].transAxes)
        else:
            axes[3].plot(power["date"], power["power_w"], marker="o", color="#4fd48e")
        axes[3].set_title("Estimated average power per session")
        axes[3].set_ylabel("Watts (estimated)")
        axes[3].grid(True, alpha=0.3)

    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def get_latest_bodyweight(db_path=None):
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), "data", "workouts_snapshot.db")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT weight FROM body_weight ORDER BY date DESC LIMIT 1").fetchone()
    conn.close()
    return row[0] if row else DEFAULT_BODYWEIGHT_LBS


def add_volume(sets):
    """Volume = weight * reps per set (0 for bodyweight/non-numeric-rep sets)."""
    sets = sets.copy()
    w = sets["weight"].fillna(0)
    sets["volume"] = np.where(sets["reps_numeric"].notna(), w * sets["reps_numeric"], np.nan)
    return sets


def add_power(sets, bodyweight_lbs=None):
    """Adds estimated watts per set. NaN where we don't have a ROM assumption or reps aren't numeric."""
    sets = sets.copy()
    if sets.empty:
        sets["power_w"] = pd.Series(dtype="float64")
        return sets
    if bodyweight_lbs is None:
        bodyweight_lbs = DEFAULT_BODYWEIGHT_LBS

    def _row_power(row):
        rom = ROM_METERS.get(row["exercise"])
        reps = row["reps_numeric"]
        if rom is None or pd.isna(reps) or reps <= 0:
            return np.nan
        if row["exercise"] in BODYWEIGHT_FRACTION:
            mass_kg = bodyweight_lbs * BODYWEIGHT_FRACTION[row["exercise"]] * LB_TO_KG
        elif pd.notna(row["weight"]) and row["weight"] > 0:
            mass_kg = row["weight"] * LB_TO_KG
        else:
            return np.nan
        work_j = mass_kg * G * rom * reps
        time_s = reps * SEC_PER_REP
        return work_j / time_s

    sets["power_w"] = sets.apply(_row_power, axis=1)
    return sets


def session_summary(sets):
    """Per-session totals: volume and mean estimated power, for trajectory plots."""
    return sets.groupby(["session_id", "date"]).agg(
        total_volume=("volume", "sum"),
        avg_power_w=("power_w", "mean"),
    ).reset_index().sort_values("date")


def plot_weight_trajectory(sets, workout_name):
    exercises = sets["exercise"].unique()
    fig, ax = plt.subplots(figsize=(9, 5))
    for ex in exercises:
        sub = sets[(sets["exercise"] == ex) & sets["weight"].notna()]
        if sub.empty:
            continue
        by_date = sub.groupby("date")["weight"].max()
        ax.plot(by_date.index, by_date.values, marker="o", label=ex)
    ax.set_title(f"{workout_name} — top set weight by session")
    ax.set_xlabel("Date")
    ax.set_ylabel("Weight (lbs)")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    return fig


def plot_volume_trajectory(summary, workout_name):
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(summary["date"].dt.strftime("%Y-%m-%d"), summary["total_volume"], color="#7c5cbf")
    ax.set_title(f"{workout_name} — total volume per session (lbs x reps)")
    ax.set_ylabel("Volume")
    ax.grid(True, axis="y", alpha=0.3)
    return fig


def plot_power_trajectory(summary, workout_name):
    fig, ax = plt.subplots(figsize=(9, 4))
    valid = summary.dropna(subset=["avg_power_w"])
    if valid.empty:
        ax.text(0.5, 0.5, "No power estimate available for this day's exercises yet",
                ha="center", va="center", transform=ax.transAxes)
    else:
        ax.plot(valid["date"], valid["avg_power_w"], marker="o", color="#4f8ef7")
    ax.set_title(f"{workout_name} — estimated average power per session")
    ax.set_xlabel("Date")
    ax.set_ylabel("Watts (estimated)")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    return fig
