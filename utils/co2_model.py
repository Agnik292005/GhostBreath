"""
GhostBreath – CO₂ Room Buildup Model
======================================
Simulates indoor CO₂ concentration in a closed study room using a
first-order mass-balance ODE (well-mixed room assumption).

Mass Balance ODE
----------------
    V × dC/dt = Q_human × 1e6  −  V × (ACH/3600) × (C − C_ambient)

    dC/dt = Q_human × 1e6 / V  −  (ACH/3600) × (C − C_ambient)

where:
    C          : CO₂ concentration [ppm]
    V          : room volume [m³]
    Q_human    : human CO₂ production rate [m³/s of pure CO₂]
    ACH        : air changes per hour [h⁻¹]
    C_ambient  : outdoor CO₂ level [ppm], default 420 ppm

Analytical Solution (constant ACH)
------------------------------------
    C_ss  = C_ambient + Q_human × 1e6 × 3600 / (V × ACH)     [steady state]
    C(t)  = C_ss + (C0 − C_ss) × exp(−ACH/3600 × t)           [transient]

For time-varying ACH (ventilation events), the ODE is solved numerically
using scipy.integrate.solve_ivp over piecewise-constant ACH segments.

Typical Values
--------------
    Q_human at rest   : 4–5 mL/s  (240–300 mL/min CO₂ pure)
    Q_human, coding   : 5–7 mL/s  (MET ≈ 1.5)
    Hostel room ACH   : 0.1–0.5   (windows closed)
    Open window ACH   : 2–5       (natural ventilation)
    C_ambient         : 420 ppm   (global average 2024)

References
----------
- Du et al. (2020). CO₂ concentration and cognitive performance in classrooms.
- Zhang et al. (2023). Indoor CO₂ and occupant wellbeing.
- ASHRAE Standard 62.1-2022, Ventilation for acceptable indoor air quality.
- Harvard CogFx study, Allen et al. (2016).
"""

import numpy as np
from scipy.integrate import solve_ivp


# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

DEFAULT_ROOM = {
    "V_room":    27.0,    # m³  (3 m × 3 m × 3 m hostel room)
    "ACH":       0.3,     # h⁻¹ (windows closed, minimal infiltration)
    "C_ambient": 420.0,   # ppm (outdoor CO₂, global average 2024)
    "C0":        420.0,   # ppm (initial indoor CO₂ = ambient)
}

# Human metabolic CO₂ production [m³/s of pure CO₂]
METABOLIC_RATES = {
    "sleeping":       3.0e-6,   # 180 mL/min
    "resting":        4.0e-6,   # 240 mL/min  (seated, reading lightly)
    "light_study":    5.0e-6,   # 300 mL/min  (plan default, typing/notes)
    "active_coding":  6.5e-6,   # 390 mL/min  (focused problem solving)
    "exercise_light": 10.0e-6,  # 600 mL/min  (standing, pacing)
}

# CO₂ impairment thresholds [ppm]  (Harvard CogFx / ASHRAE guidance)
THRESHOLDS = {
    1000: ("Mild impairment",       "#f9c74f"),   # yellow
    1500: ("Significant impairment","#f3722c"),   # orange
    2500: ("Severe impairment",     "#d62728"),   # red
}


# ---------------------------------------------------------------------------
# Analytical model (constant ACH)
# ---------------------------------------------------------------------------

def steady_state(V_room, Q_human, ACH, C_ambient=420.0):
    """
    Analytical steady-state CO₂ concentration [ppm].

        C_ss = C_ambient + Q_human × 1e6 × 3600 / (V × ACH)

    Parameters
    ----------
    V_room    : float  Room volume [m³]
    Q_human   : float  CO₂ production rate [m³/s of pure CO₂]
    ACH       : float  Air changes per hour [h⁻¹]
    C_ambient : float  Outdoor CO₂ [ppm]

    Returns
    -------
    C_ss : float  Steady-state concentration [ppm]
    """
    return C_ambient + Q_human * 1e6 * 3600.0 / (V_room * ACH)


def co2_analytical(t, V_room, Q_human, ACH, C_ambient=420.0, C0=420.0):
    """
    Analytical CO₂ concentration vs time (constant ACH).

        C(t) = C_ss + (C0 − C_ss) × exp(−ACH/3600 × t)

    Parameters
    ----------
    t         : float or ndarray  Time [s]
    V_room    : float             Room volume [m³]
    Q_human   : float             CO₂ production rate [m³/s]
    ACH       : float             Air changes per hour [h⁻¹]
    C_ambient : float             Outdoor CO₂ [ppm]
    C0        : float             Initial CO₂ [ppm]

    Returns
    -------
    C : float or ndarray  CO₂ concentration [ppm]
    """
    C_ss = steady_state(V_room, Q_human, ACH, C_ambient)
    tau  = 3600.0 / ACH          # time constant [s]
    return C_ss + (C0 - C_ss) * np.exp(-t / tau)


def time_to_threshold(threshold, V_room, Q_human, ACH,
                       C_ambient=420.0, C0=420.0):
    """
    Analytical time [s] to reach a CO₂ threshold (constant ACH).

    Returns np.inf if the threshold is never reached (C_ss < threshold).

    Parameters
    ----------
    threshold : float  Target CO₂ level [ppm]
    V_room, Q_human, ACH, C_ambient, C0 : see co2_analytical

    Returns
    -------
    t_reach : float  Time to reach threshold [s], or np.inf
    """
    C_ss = steady_state(V_room, Q_human, ACH, C_ambient)
    if C0 >= threshold:
        return 0.0
    if threshold >= C_ss:
        return np.inf
    tau = 3600.0 / ACH
    ratio = (threshold - C_ss) / (C0 - C_ss)   # 0 < ratio < 1
    return -tau * np.log(ratio)


# ---------------------------------------------------------------------------
# Numerical ODE solver (time-varying ACH via ventilation events)
# ---------------------------------------------------------------------------

def _build_rhs(V_room, Q_human, ACH_base, C_ambient, ach_events=None):
    """
    Build the ODE right-hand side function with optional time-varying ACH.

    ach_events : list of (t_start_s, t_end_s, ACH_value) tuples
                 Piecewise-constant ACH overrides during [t_start, t_end].
    """
    def rhs(t, C):
        ach = ACH_base
        if ach_events:
            for t0_ev, t1_ev, ach_ev in ach_events:
                if t0_ev <= t <= t1_ev:
                    ach = ach_ev
                    break
        source = Q_human * 1e6 / V_room          # ppm/s from occupant
        vent   = (ach / 3600.0) * (C_ambient - C[0])   # ppm/s from ventilation
        return [source + vent]
    return rhs


def solve_co2(t_span, V_room, Q_human, ACH, C_ambient=420.0, C0=420.0,
              ach_events=None, n_points=14400):
    """
    Numerically solve the CO₂ ODE, optionally with ventilation events.

    Parameters
    ----------
    t_span     : (t0, tf)  Simulation time span [s]
    V_room     : float     Room volume [m³]
    Q_human    : float     CO₂ production rate [m³/s of pure CO₂]
    ACH        : float     Baseline air changes per hour [h⁻¹]
    C_ambient  : float     Outdoor CO₂ [ppm]
    C0         : float     Initial CO₂ [ppm]
    ach_events : list      [(t_start, t_end, ACH_high), ...] ventilation events
    n_points   : int       Number of output time points

    Returns
    -------
    t : ndarray  Time array [s]
    C : ndarray  CO₂ concentration [ppm]
    """
    t_eval = np.linspace(t_span[0], t_span[1], n_points)

    # Build breakpoints to ensure fine resolution at event transitions
    breakpoints = set([t_span[0], t_span[1]])
    if ach_events:
        for t0_ev, t1_ev, _ in ach_events:
            breakpoints.update([t0_ev, t1_ev])
    breakpoints = sorted(breakpoints)

    t_out, C_out = [], []
    C_current = C0

    for i in range(len(breakpoints) - 1):
        seg_t0 = breakpoints[i]
        seg_t1 = breakpoints[i + 1]
        if seg_t0 >= seg_t1:
            continue

        # Determine ACH for this segment
        ach_seg = ACH
        if ach_events:
            for t0_ev, t1_ev, ach_ev in ach_events:
                if seg_t0 >= t0_ev and seg_t1 <= t1_ev:
                    ach_seg = ach_ev
                    break

        def rhs(t, C, _ach=ach_seg):
            source = Q_human * 1e6 / V_room
            vent   = (_ach / 3600.0) * (C_ambient - C[0])
            return [source + vent]

        # t_eval points within this segment
        seg_eval = t_eval[(t_eval >= seg_t0) & (t_eval <= seg_t1)]
        if len(seg_eval) == 0:
            seg_eval = np.array([seg_t0, seg_t1])

        sol = solve_ivp(rhs, [seg_t0, seg_t1], [C_current],
                        t_eval=seg_eval, method='RK45',
                        rtol=1e-7, atol=1e-5)

        if i == 0:
            t_out.extend(sol.t.tolist())
            C_out.extend(sol.y[0].tolist())
        else:
            t_out.extend(sol.t[1:].tolist())
            C_out.extend(sol.y[0][1:].tolist())

        C_current = sol.y[0][-1]

    return np.array(t_out), np.array(C_out)


# ---------------------------------------------------------------------------
# Multi-occupant model
# ---------------------------------------------------------------------------

def multi_occupant_q(n_people, q_per_person=5.0e-6):
    """
    Total CO₂ production rate for n_people occupants [m³/s].

    Parameters
    ----------
    n_people     : int    Number of occupants
    q_per_person : float  CO₂ rate per person [m³/s], default 5e-6

    Returns
    -------
    Q_total : float  Total CO₂ production [m³/s]
    """
    return n_people * q_per_person


# ---------------------------------------------------------------------------
# Parameter sweep for heatmap
# ---------------------------------------------------------------------------

def heatmap_time_to_threshold(V_room_values, ACH_values,
                               threshold=1000.0, Q_human=5.0e-6,
                               C_ambient=420.0, C0=420.0):
    """
    Compute time-to-threshold matrix for a 2D parameter sweep.

    Parameters
    ----------
    V_room_values : array-like  Room volumes to sweep [m³]
    ACH_values    : array-like  Air changes per hour to sweep [h⁻¹]
    threshold     : float       CO₂ threshold [ppm]
    Q_human       : float       CO₂ production rate [m³/s]
    C_ambient     : float       Outdoor CO₂ [ppm]
    C0            : float       Initial CO₂ [ppm]

    Returns
    -------
    times_min : 2D ndarray  Time-to-threshold in minutes
                            shape (len(V_room_values), len(ACH_values))
                            np.inf where threshold is never reached.
    """
    V_arr  = np.asarray(V_room_values, dtype=float)
    A_arr  = np.asarray(ACH_values,    dtype=float)
    result = np.full((len(V_arr), len(A_arr)), np.nan)

    for i, V in enumerate(V_arr):
        for j, A in enumerate(A_arr):
            t_s = time_to_threshold(threshold, V, Q_human, A, C_ambient, C0)
            result[i, j] = t_s / 60.0 if np.isfinite(t_s) else np.inf

    return result


# ---------------------------------------------------------------------------
# Ventilation event helpers
# ---------------------------------------------------------------------------

def window_open_event(t_open_min, duration_min, ACH_open=3.0):
    """
    Create a ventilation event tuple for a window opening.

    Parameters
    ----------
    t_open_min    : float  Time at which window opens [minutes]
    duration_min  : float  Duration window stays open [minutes]
    ACH_open      : float  ACH while window is open [h⁻¹]

    Returns
    -------
    event : tuple  (t_start_s, t_end_s, ACH_value)
    """
    t_start = t_open_min * 60.0
    t_end   = (t_open_min + duration_min) * 60.0
    return (t_start, t_end, ACH_open)


def time_to_recover(C_high, C_target, V_room, Q_human, ACH_high,
                    C_ambient=420.0):
    """
    Time to recover from elevated CO₂ to C_target during increased ventilation.

    Parameters
    ----------
    C_high    : float  Starting elevated CO₂ [ppm]
    C_target  : float  Target recovery CO₂ [ppm]
    V_room    : float  Room volume [m³]
    Q_human   : float  CO₂ production rate [m³/s]
    ACH_high  : float  High ventilation ACH during recovery [h⁻¹]
    C_ambient : float  Outdoor CO₂ [ppm]

    Returns
    -------
    t_recover : float  Recovery time [s], or np.inf if impossible
    """
    C_ss_high = steady_state(V_room, Q_human, ACH_high, C_ambient)
    if C_target <= C_ss_high:
        return np.inf
    if C_high <= C_target:
        return 0.0
    tau = 3600.0 / ACH_high
    ratio = (C_target - C_ss_high) / (C_high - C_ss_high)
    return -tau * np.log(ratio)


# ---------------------------------------------------------------------------
# Convenience: scenario summary
# ---------------------------------------------------------------------------

def scenario_summary(V_room, Q_human, ACH, C_ambient=420.0, C0=420.0):
    """
    Print a summary of CO₂ dynamics for a given scenario.

    Returns
    -------
    dict with keys: C_ss, t_1000_min, t_1500_min, t_2500_min, tau_min
    """
    C_ss = steady_state(V_room, Q_human, ACH, C_ambient)
    tau  = 3600.0 / ACH / 60.0   # time constant in minutes

    results = {
        "C_ss_ppm":   C_ss,
        "tau_min":    tau,
    }
    for threshold in [1000, 1500, 2500]:
        key = f"t_{threshold}_min"
        t_s = time_to_threshold(threshold, V_room, Q_human, ACH, C_ambient, C0)
        results[key] = t_s / 60.0 if np.isfinite(t_s) else np.inf

    return results
