"""
GhostBreath – TEG (Thermoelectric Generator) Physics Model
===========================================================
Models a TEC1-12706 Peltier module used in reverse as a TEG.

Specifications (TEC1-12706 datasheet at 300 K):
  N  = 127  thermocouple couples
  α  = 200  µV/K  Seebeck coefficient per couple
  Ri = 1.2  Ω     internal resistance at room temperature
  K  = 0.5  W/K   thermal conductance of the module

All functions accept either scalar or NumPy array inputs.
"""

import numpy as np


# ---------------------------------------------------------------------------
# Default TEG parameters (TEC1-12706)
# ---------------------------------------------------------------------------
DEFAULT_PARAMS = {
    "N": 127,           # number of thermocouple couples
    "alpha": 200e-6,    # Seebeck coefficient per couple [V/K]
    "R_int": 1.2,       # internal electrical resistance [Ω]
    "K_teg": 0.5,       # thermal conductance [W/K]
}


# ---------------------------------------------------------------------------
# Core electrical model
# ---------------------------------------------------------------------------

def open_circuit_voltage(delta_T, N=127, alpha=200e-6):
    """
    Compute the TEG open-circuit voltage using the Seebeck equation.

        V_oc = N × α × ΔT

    Parameters
    ----------
    delta_T : float or ndarray  Temperature difference hot-side minus cold-side [K or °C]
    N       : int               Number of thermocouple couples
    alpha   : float             Seebeck coefficient per couple [V/K]

    Returns
    -------
    V_oc : float or ndarray  Open-circuit voltage [V]
    """
    return N * alpha * delta_T


def matched_load_voltage(delta_T, N=127, alpha=200e-6):
    """
    Voltage across a matched load (R_load = R_int).
    At maximum power transfer, V_load = V_oc / 2.

    Parameters
    ----------
    delta_T : float or ndarray  Temperature difference [K or °C]
    N, alpha: TEG parameters (see open_circuit_voltage)

    Returns
    -------
    V_load : float or ndarray  Load voltage at maximum power transfer [V]
    """
    return open_circuit_voltage(delta_T, N, alpha) / 2.0


def max_power(delta_T, N=127, alpha=200e-6, R_int=1.2):
    """
    Maximum electrical power output (at matched load R_load = R_int).

        P_max = V_oc² / (4 × R_int)

    Parameters
    ----------
    delta_T : float or ndarray  Temperature difference [K or °C]
    N, alpha: TEG electrical parameters
    R_int   : float             Internal resistance [Ω]

    Returns
    -------
    P_max : float or ndarray  Maximum power output [W]
    """
    V_oc = open_circuit_voltage(delta_T, N, alpha)
    return (V_oc ** 2) / (4.0 * R_int)


def output_current(delta_T, N=127, alpha=200e-6, R_int=1.2):
    """
    Short-circuit current (I_sc) and matched-load current (I_max).

    At matched load: I_max = V_oc / (2 × R_int)

    Returns
    -------
    dict with keys 'I_sc' and 'I_max' [A]
    """
    V_oc = open_circuit_voltage(delta_T, N, alpha)
    I_sc = V_oc / R_int
    I_max = V_oc / (2.0 * R_int)
    return {"I_sc": I_sc, "I_max": I_max}


# ---------------------------------------------------------------------------
# Thermal model – effective ΔT across the TEG accounting for heatsink
# ---------------------------------------------------------------------------

def effective_delta_T(T_source, T_ambient, R_heatsink, K_teg=0.5):
    """
    Compute the actual temperature difference across the TEG junctions,
    accounting for heatsink thermal resistance on the cold side.

    Thermal circuit:
        T_source → [TEG thermal resistance 1/K_teg] → T_hot_junction
        T_cold_junction → [R_heatsink] → T_ambient

    With an ideal (zero-resistance) hot-side contact, T_hot = T_source.
    The cold junction rises above ambient due to finite heatsink resistance:

        ΔT_eff = T_source - T_cold
        T_cold = T_ambient + Q_out × R_heatsink

    Under open-circuit conditions (no electrical load), the heat flux
    through the TEG is approximately:
        Q ≈ K_teg × (T_source - T_ambient)    [W]

    This gives:
        T_cold = T_ambient + K_teg × (T_source - T_ambient) × R_heatsink
        ΔT_eff = (T_source - T_ambient) × (1 - K_teg × R_heatsink)

    Parameters
    ----------
    T_source   : float or ndarray  Hot-side temperature (laptop exhaust) [°C or K]
    T_ambient  : float             Ambient (room) temperature [°C or K]
    R_heatsink : float             Heatsink thermal resistance [K/W]
                                   Typical small passive HS: 5–20 K/W
    K_teg      : float             TEG thermal conductance [W/K]

    Returns
    -------
    delta_T_eff : float or ndarray  Effective ΔT across TEG junctions [K]
    T_cold      : float or ndarray  Cold-junction temperature [same unit as input]
    """
    delta_T_raw = T_source - T_ambient
    # Heat flowing through TEG at open circuit
    Q = K_teg * delta_T_raw
    T_cold = T_ambient + Q * R_heatsink
    delta_T_eff = T_source - T_cold
    return delta_T_eff, T_cold


def heatsink_sweep(delta_T_source, R_hs_values, K_teg=0.5, N=127, alpha=200e-6, R_int=1.2):
    """
    Sweep heatsink thermal resistance values and return effective ΔT and P_max.

    Parameters
    ----------
    delta_T_source : float       Raw source–ambient temperature difference [K]
    R_hs_values    : array-like  Heatsink resistance values to sweep [K/W]
    K_teg, N, alpha, R_int: TEG parameters

    Returns
    -------
    dict with keys:
        'R_hs'       : array of heatsink resistance values
        'delta_T_eff': array of effective ΔT values across TEG
        'P_max'      : array of maximum power output [W]
        'P_max_mW'   : array of maximum power output [mW]
    """
    R_hs_arr = np.asarray(R_hs_values, dtype=float)
    # Effective ΔT = delta_T_source × (1 - K_teg × R_hs)
    delta_T_eff = delta_T_source * (1.0 - K_teg * R_hs_arr)
    delta_T_eff = np.clip(delta_T_eff, 0, None)   # ΔT can't be negative
    P = max_power(delta_T_eff, N=N, alpha=alpha, R_int=R_int)
    return {
        "R_hs": R_hs_arr,
        "delta_T_eff": delta_T_eff,
        "P_max": P,
        "P_max_mW": P * 1e3,
    }


# ---------------------------------------------------------------------------
# Boost converter model
# ---------------------------------------------------------------------------

def boost_output_power(P_teg, eta=0.80):
    """
    Usable power after the BQ25570 boost converter (η ≈ 80%).

    Parameters
    ----------
    P_teg : float or ndarray  TEG electrical power [W]
    eta   : float             Converter efficiency (0–1)

    Returns
    -------
    P_out : float or ndarray  Power available to system [W]
    """
    return P_teg * eta


# ---------------------------------------------------------------------------
# Convenience: summary table at key ΔT values
# ---------------------------------------------------------------------------

def summary_table(delta_T_values, N=127, alpha=200e-6, R_int=1.2, eta_boost=0.80):
    """
    Return a dict-of-lists summary at specified ΔT breakpoints.

    Parameters
    ----------
    delta_T_values : list of float  Temperature differences to evaluate [K]

    Returns
    -------
    dict with lists: 'delta_T', 'V_oc_mV', 'V_load_mV', 'P_max_mW', 'P_boost_mW'
    """
    dt = np.asarray(delta_T_values, dtype=float)
    V_oc = open_circuit_voltage(dt, N, alpha)
    V_load = matched_load_voltage(dt, N, alpha)
    P_max = max_power(dt, N, alpha, R_int)
    P_boost = boost_output_power(P_max, eta_boost)
    return {
        "delta_T_C": dt.tolist(),
        "V_oc_mV": (V_oc * 1e3).tolist(),
        "V_load_mV": (V_load * 1e3).tolist(),
        "P_max_mW": (P_max * 1e3).tolist(),
        "P_boost_mW": (P_boost * 1e3).tolist(),
    }
