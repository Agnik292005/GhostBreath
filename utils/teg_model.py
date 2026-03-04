"""
GhostBreath – TEG (Thermoelectric Generator) Physics Model
===========================================================
Models a TEC1-12706 Peltier module used in reverse as a TEG.

Specifications (TEC1-12706 datasheet at 300 K):
  N  = 127  thermocouple couples
  α  = 200  µV/K  Seebeck coefficient per couple
  Ri = 1.2  Ω     internal resistance at room temperature
  K  = 0.5  W/K   thermal conductance of the module

Thermal Resistance Model (v2 – realistic coupling)
---------------------------------------------------
In practice a clip-on TEG does NOT see the full exhaust-to-ambient ΔT.
Three thermal resistances act in series from exhaust air to ambient:

    T_exhaust → [R_contact_hot] → T_hot → [R_teg = 1/K_teg] → T_cold → [R_hs] → T_ambient

  R_contact_hot : hot-side contact / convective resistance [K/W]
                  Imperfect clip contact + exhaust-to-solid convection.
                  Typical range: 1–4 K/W for a clip-on attachment.
  R_teg = 1/K_teg : TEG thermal resistance [K/W]  (= 2 K/W for TEC1-12706)
  R_hs          : cold-side heatsink resistance [K/W]
                  Natural convection on exposed cold face: 1–3 K/W.

Thermal coupling factor:
  η_th = R_teg / (R_contact_hot + R_teg + R_hs)

Realistic values → η_th ≈ 0.40–0.60 (40–60% of exhaust ΔT across TEG).
Default realistic preset: R_contact_hot=2.0, R_hs=0.0 → η_th=0.50.
(Simpler preset keeps cold-side resistance in R_hs separately.)

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

# Realistic thermal coupling defaults for a clip-on device
# R_contact_hot = 2.0 K/W  (clip contact resistance to laptop exhaust)
# R_hs          = 1.0 K/W  (passive cold-side spreader / short fin)
# R_teg         = 1/0.5 = 2.0 K/W
# η_th = 2.0 / (2.0 + 2.0 + 1.0) = 0.40  → 40 % coupling (conservative)
REALISTIC_THERMAL_PARAMS = {
    "R_contact_hot": 2.0,   # [K/W] hot-side contact resistance
    "R_hs": 1.0,            # [K/W] cold-side heatsink resistance
    # Resulting η_th at these defaults ≈ 40 %
}

# Mid-range preset: η_th = 50 %
# R_contact_hot=1.5, R_hs=0.5 → 2/(1.5+2+0.5)=2/4=0.50
MODERATE_THERMAL_PARAMS = {
    "R_contact_hot": 1.5,
    "R_hs": 0.5,
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
# Thermal model – series resistance circuit (realistic coupling)
# ---------------------------------------------------------------------------

def thermal_coupling_factor(K_teg=0.5, R_contact_hot=2.0, R_hs=1.0):
    """
    Fraction of exhaust-to-ambient ΔT that appears across the TEG junctions.

    Full series thermal circuit:
        T_exhaust → [R_contact_hot] → T_hot → [R_teg] → T_cold → [R_hs] → T_ambient

        η_th = R_teg / (R_contact_hot + R_teg + R_hs)

    For a clip-on device η_th typically falls in the range 0.40–0.60.

    Parameters
    ----------
    K_teg         : float  TEG thermal conductance [W/K]  (R_teg = 1/K_teg)
    R_contact_hot : float  Hot-side contact resistance [K/W]
    R_hs          : float  Cold-side heatsink resistance [K/W]

    Returns
    -------
    eta_th : float  Thermal coupling factor (0–1)
    """
    R_teg = 1.0 / K_teg
    R_total = R_contact_hot + R_teg + R_hs
    return R_teg / R_total


def effective_delta_T(T_source, T_ambient, R_heatsink, K_teg=0.5, R_contact_hot=0.0):
    """
    Compute the actual temperature difference across the TEG junctions,
    accounting for thermal resistances on both hot and cold sides.

    Full series thermal circuit:
        T_exhaust → [R_contact_hot] → T_hot → [R_teg=1/K_teg] → T_cold → [R_hs] → T_ambient

    Heat flux through the series circuit:
        Q = (T_exhaust − T_ambient) / (R_contact_hot + R_teg + R_hs)

    Junction temperatures:
        T_hot  = T_exhaust − Q × R_contact_hot
        T_cold = T_ambient + Q × R_hs

    Effective ΔT across TEG:
        ΔT_eff = T_hot − T_cold = Q / K_teg
               = (T_exhaust − T_ambient) × R_teg / (R_contact_hot + R_teg + R_hs)
               = (T_exhaust − T_ambient) × η_th

    With R_contact_hot = 0 (ideal hot contact, v1 behaviour):
        ΔT_eff = (T_source − T_ambient) / (1 + K_teg × R_heatsink)

    Parameters
    ----------
    T_source      : float or ndarray  Exhaust air temperature [°C or K]
    T_ambient     : float             Ambient (room) temperature [°C or K]
    R_heatsink    : float             Cold-side heatsink resistance [K/W]
    K_teg         : float             TEG thermal conductance [W/K]
    R_contact_hot : float             Hot-side contact resistance [K/W]
                                      0 = perfect contact (v1 / ideal case)
                                      1–4 K/W = realistic clip-on attachment

    Returns
    -------
    delta_T_eff : float or ndarray  Effective ΔT across TEG junctions [K]
    T_cold      : float or ndarray  Cold-junction temperature [same unit as input]
    """
    R_teg = 1.0 / K_teg
    R_total = R_contact_hot + R_teg + R_heatsink
    delta_T_raw = T_source - T_ambient
    Q = delta_T_raw / R_total
    T_hot = T_source - Q * R_contact_hot
    T_cold = T_ambient + Q * R_heatsink
    delta_T_eff = T_hot - T_cold          # = Q * R_teg
    delta_T_eff = np.maximum(delta_T_eff, 0.0)   # physical floor
    return delta_T_eff, T_cold


def heatsink_sweep(delta_T_source, R_hs_values, K_teg=0.5,
                   N=127, alpha=200e-6, R_int=1.2, R_contact_hot=0.0):
    """
    Sweep heatsink thermal resistance values and return effective ΔT and P_max.

    Parameters
    ----------
    delta_T_source : float       Raw source–ambient temperature difference [K]
    R_hs_values    : array-like  Heatsink resistance values to sweep [K/W]
    K_teg, N, alpha, R_int      TEG parameters
    R_contact_hot  : float       Hot-side contact resistance [K/W] (default 0)

    Returns
    -------
    dict with keys:
        'R_hs'       : array of heatsink resistance values [K/W]
        'delta_T_eff': array of effective ΔT values across TEG [K]
        'P_max'      : array of maximum power output [W]
        'P_max_mW'   : array of maximum power output [mW]
    """
    R_hs_arr = np.asarray(R_hs_values, dtype=float)
    R_teg = 1.0 / K_teg
    # Series resistance divider
    R_total = R_contact_hot + R_teg + R_hs_arr
    delta_T_eff = delta_T_source * R_teg / R_total
    delta_T_eff = np.clip(delta_T_eff, 0, None)
    P = max_power(delta_T_eff, N=N, alpha=alpha, R_int=R_int)
    return {
        "R_hs": R_hs_arr,
        "delta_T_eff": delta_T_eff,
        "P_max": P,
        "P_max_mW": P * 1e3,
    }


def realistic_teg_power(delta_T_source, coupling_lo=0.40, coupling_hi=0.60,
                         N=127, alpha=200e-6, R_int=1.2, eta_boost=0.80):
    """
    Compute TEG power output across a range of thermal coupling factors.

    Wraps the series-resistance model into a simple coupling-factor interface.
    Returns the lower-bound, midpoint, and upper-bound power given that
    η_th lies in [coupling_lo, coupling_hi].

    Parameters
    ----------
    delta_T_source : float or ndarray  Exhaust-to-ambient ΔT [K]
    coupling_lo    : float             Lower bound of thermal coupling (e.g. 0.40)
    coupling_hi    : float             Upper bound of thermal coupling (e.g. 0.60)
    N, alpha, R_int: TEG electrical parameters
    eta_boost      : float             Boost converter efficiency (0–1)

    Returns
    -------
    dict with keys:
        'delta_T_teg_lo'  : effective ΔT at coupling_lo
        'delta_T_teg_mid' : effective ΔT at mid coupling
        'delta_T_teg_hi'  : effective ΔT at coupling_hi
        'P_boost_lo_mW'   : P_boost at coupling_lo [mW]
        'P_boost_mid_mW'  : P_boost at mid coupling [mW]
        'P_boost_hi_mW'   : P_boost at coupling_hi [mW]
    """
    dt = np.asarray(delta_T_source, dtype=float)
    coupling_mid = 0.5 * (coupling_lo + coupling_hi)

    def _pbmw(eta):
        return boost_output_power(max_power(eta * dt, N, alpha, R_int), eta_boost) * 1e3

    return {
        "delta_T_teg_lo":   coupling_lo  * dt,
        "delta_T_teg_mid":  coupling_mid * dt,
        "delta_T_teg_hi":   coupling_hi  * dt,
        "P_boost_lo_mW":    _pbmw(coupling_lo),
        "P_boost_mid_mW":   _pbmw(coupling_mid),
        "P_boost_hi_mW":    _pbmw(coupling_hi),
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
