"""utils/fatigue_model.py
=======================
GhostBreath – Cognitive Fatigue Risk Model
Module 4: Convert CO₂ readings → fatigue risk score

Physics-inspired, lightweight weighted-sigmoid model.
Designed for interpretability and ESP32-C3 fixed-point implementation.

Model inputs (all produced by Modules 1–3):
    C           – CO₂ concentration [ppm]         (Module 3 / SCD41 reading)
    dCdt        – rate of change [ppm/min]         (finite-diff on readings)
    study_time  – elapsed study time [min]         (system clock)

Model output:
    score       – fatigue risk score ∈ [0, 1]
    label       – "Safe" | "Mild Fatigue" | "High Fatigue"

Scoring formula (weighted sum of three sigmoid sub-scores):
    score = w_co2 · f_co2(C) + w_rate · f_rate(dCdt) + w_time · f_time(t)

    f_co2  – logistic function of CO₂, centred at 1250 ppm
             (midpoint of mild–significant impairment band 1000–1500 ppm)
    f_rate – linear normalisation of dC/dt onto [0, 1]
    f_time – logistic function of study time, centred at 90 min

Default weights: CO₂ 60 % | rate 20 % | time 20 %
    – CO₂ is the primary physical driver (Allen et al. 2016 Harvard CogFx)
    – Rate of change adds early-warning sensitivity (rising CO₂ = rising risk)
    – Study time encodes cumulative cognitive load independent of CO₂

Score thresholds:
    0.00 – 0.30 : Safe
    0.30 – 0.60 : Mild Fatigue  (CO₂ typically 1000–1500 ppm at this score)
    0.60 – 1.00 : High Fatigue  (CO₂ typically > 1400 ppm, or long session)

Reference:
    Allen et al. (2016) "Associations of Cognitive Function Scores with Carbon
    Dioxide, Ventilation, and Volatile Organic Compound Exposures in Office
    Workers", Environmental Health Perspectives.
    CO₂ at 1000 ppm reduces cognitive performance by ~15 %; at 2500 ppm by ~50%.
"""

import numpy as np

from utils.co2_model import (
    solve_co2,
    DEFAULT_ROOM,
    METABOLIC_RATES,
    THRESHOLDS,
)

# ── CO₂ classification thresholds (ppm) ─────────────────────────────────────
CO2_THRESHOLDS = {
    "safe":  1000,
    "mild":  1500,
    "high":  2500,
}

# ── Fatigue score thresholds ─────────────────────────────────────────────────
SCORE_THRESHOLDS = {
    "safe": 0.30,   # below → Safe
    "mild": 0.60,   # below → Mild Fatigue, above → High Fatigue
}

# ── Default model weights (must sum to 1) ────────────────────────────────────
DEFAULT_WEIGHTS = {
    "w_co2":  0.60,
    "w_rate": 0.20,
    "w_time": 0.20,
}

# ── Sigmoid / normalisation parameters ───────────────────────────────────────
# CO₂ sigmoid: f_co2 ≈ 0.04 at 420 ppm, 0.50 at 1250 ppm, 0.97 at 2500 ppm
_CO2_CENTRE = 1250.0   # ppm – midpoint of mild–significant threshold band
_CO2_SCALE  = 0.0040   # logistic steepness [ppm⁻¹]

# Study-time sigmoid: f_time ≈ 0.05 at 0 min, 0.50 at 90 min, 0.95 at 180 min
_TIME_CENTRE = 90.0    # min – centre of fatigue accumulation curve
_TIME_SCALE  = 0.033   # logistic steepness [min⁻¹]

# Rate normalisation: ±15 ppm/min spans the realistic dynamic range
_RATE_MAX = 15.0       # ppm/min


# ── Sub-score functions (each returns a value in [0, 1]) ─────────────────────

def _f_co2(C):
    """CO₂ sub-score via logistic function centred at 1250 ppm.

    Parameters
    ----------
    C : float or ndarray – CO₂ concentration [ppm]

    Returns
    -------
    float or ndarray in [0, 1]
    """
    return 1.0 / (1.0 + np.exp(-_CO2_SCALE * (np.asarray(C, float) - _CO2_CENTRE)))


def _f_rate(dCdt):
    """Rate-of-change sub-score.

    Maps dC/dt ∈ [−15, +15] ppm/min linearly onto [0, 1].
    Rapid rise → 1.0 ; stable → 0.5 ; falling CO₂ → 0.0

    Parameters
    ----------
    dCdt : float or ndarray – rate of change [ppm/min]

    Returns
    -------
    float or ndarray in [0, 1]
    """
    norm = np.clip(np.asarray(dCdt, float) / _RATE_MAX, -1.0, 1.0)
    return (norm + 1.0) / 2.0


def _f_time(study_time_min):
    """Study-duration sub-score via logistic function centred at 90 min.

    Parameters
    ----------
    study_time_min : float or ndarray – elapsed study time [min]

    Returns
    -------
    float or ndarray in [0, 1]
    """
    t = np.asarray(study_time_min, float)
    return 1.0 / (1.0 + np.exp(-_TIME_SCALE * (t - _TIME_CENTRE)))


# ── Public API ────────────────────────────────────────────────────────────────

def fatigue_score(C, dCdt, study_time_min,
                  w_co2=DEFAULT_WEIGHTS["w_co2"],
                  w_rate=DEFAULT_WEIGHTS["w_rate"],
                  w_time=DEFAULT_WEIGHTS["w_time"]):
    """Compute cognitive fatigue risk score ∈ [0, 1].

    Parameters
    ----------
    C              : float or ndarray – CO₂ concentration [ppm]
    dCdt           : float or ndarray – rate of change [ppm/min]
    study_time_min : float or ndarray – elapsed study time [minutes]
    w_co2          : float – weight for CO₂ component (default 0.60)
    w_rate         : float – weight for rate-of-change component (default 0.20)
    w_time         : float – weight for study-time component (default 0.20)

    Returns
    -------
    float or ndarray – fatigue risk score ∈ [0, 1]
    """
    score = (w_co2 * _f_co2(C)
             + w_rate * _f_rate(dCdt)
             + w_time * _f_time(study_time_min))
    return np.clip(score, 0.0, 1.0)


def fatigue_classification(score):
    """Classify a fatigue score into a risk level.

    Parameters
    ----------
    score : float – fatigue risk score ∈ [0, 1]

    Returns
    -------
    (label, level) : (str, int)
        label  – "Safe" | "Mild Fatigue" | "High Fatigue"
        level  – 0       | 1              | 2
    """
    score = float(score)
    if score < SCORE_THRESHOLDS["safe"]:
        return "Safe", 0
    elif score < SCORE_THRESHOLDS["mild"]:
        return "Mild Fatigue", 1
    else:
        return "High Fatigue", 2


def simulate_fatigue_over_session(
    session_duration_min=240.0,
    dt_sample_min=1.0,
    room=None,
    Q_human=None,
    ach_events=None,
    w_co2=DEFAULT_WEIGHTS["w_co2"],
    w_rate=DEFAULT_WEIGHTS["w_rate"],
    w_time=DEFAULT_WEIGHTS["w_time"],
):
    """Simulate CO₂ buildup and fatigue risk over a study session.

    Uses Module 3 CO₂ model (solve_co2) to generate CO₂ time series,
    then applies the fatigue scoring model at each sample.

    Parameters
    ----------
    session_duration_min : float  – total session length [min] (default 240)
    dt_sample_min        : float  – sampling interval [min] (default 1)
    room                 : dict   – room parameters (defaults to DEFAULT_ROOM)
    Q_human              : float  – CO₂ production [m³/s] (default: light_study)
    ach_events           : list   – ventilation events [(t_start_s, t_end_s, ACH)]
    w_co2, w_rate, w_time : float – model weights

    Returns
    -------
    dict with keys:
        t_min          – time array [min]
        C_ppm          – CO₂ concentration [ppm]
        dCdt_ppm_min   – rate of change [ppm/min]
        score          – fatigue risk score [0–1] at each time step
        level          – integer risk level (0 / 1 / 2)
        label          – string label at each time step
        alerts         – list of dicts at each level-up transition
                         (keys: t_min, score, level, label, C_ppm)
        t_1000_min     – time to cross 1000 ppm [min], or None
        t_1500_min     – time to cross 1500 ppm [min], or None
        t_2500_min     – time to cross 2500 ppm [min], or None
    """
    if room is None:
        room = DEFAULT_ROOM.copy()
    if Q_human is None:
        Q_human = METABOLIC_RATES["light_study"]
    if ach_events is None:
        ach_events = []

    n_points = int(session_duration_min / dt_sample_min) + 1
    t_s, C = solve_co2(
        t_span=(0, session_duration_min * 60.0),
        V_room=room["V_room"],
        Q_human=Q_human,
        ACH=room["ACH"],
        C_ambient=room["C_ambient"],
        C0=room.get("C0", room["C_ambient"]),
        ach_events=ach_events,
        n_points=n_points,
    )

    t_min = t_s / 60.0

    # Rate of change [ppm/min] via central differences
    dCdt = np.gradient(C, t_min)

    # Vectorised scoring
    scores = fatigue_score(C, dCdt, t_min, w_co2, w_rate, w_time)

    # Per-step classification
    labels_levels = [fatigue_classification(float(s)) for s in scores]
    label_strs = [lb for lb, _ in labels_levels]
    levels = np.array([lv for _, lv in labels_levels], dtype=int)

    # Detect upward level transitions → trigger alerts
    alerts = []
    prev_level = 0
    for i in range(len(t_min)):
        lv = int(levels[i])
        if lv > prev_level:
            alerts.append({
                "t_min":  float(t_min[i]),
                "score":  float(scores[i]),
                "level":  lv,
                "label":  label_strs[i],
                "C_ppm":  float(C[i]),
            })
            prev_level = lv

    def _t_to(threshold):
        idx = np.where(C >= threshold)[0]
        return float(t_min[idx[0]]) if len(idx) else None

    return {
        "t_min":        t_min,
        "C_ppm":        C,
        "dCdt_ppm_min": dCdt,
        "score":        scores,
        "level":        levels,
        "label":        label_strs,
        "alerts":       alerts,
        "t_1000_min":   _t_to(1000),
        "t_1500_min":   _t_to(1500),
        "t_2500_min":   _t_to(2500),
    }
