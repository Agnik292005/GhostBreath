"""
GhostBreath – Supercapacitor Energy Storage Model
==================================================
Models an EDLC (Electric Double-Layer Capacitor / supercapacitor) as the
energy buffer between the TEG boost converter output and the sensor/MCU load.

The supercapacitor is charged by the BQ25570 boost converter (fed by the TEG)
and discharged by the CO₂ sensor (SCD41) and microcontroller.

Reference device: 1 F EDLC, e.g. Murata JUWT1105MCD or Panasonic EEC-S0HD104H
  C_sc   = 1.0  F    rated capacitance
  V_max  = 2.7  V    maximum rated voltage
  V_min  = 1.0  V    minimum for BQ25570 boost converter cold-start
  ESR    = 0.05 Ω    equivalent series resistance (typical)

Energy model (constant-power charging / discharging)
------------------------------------------------------
When the TEG delivers constant power P_in into the supercapacitor:

    C · V · dV/dt = P_in
    V(t) = sqrt(V0² + 2·P_in·t / C)                   [charging]

When the load draws constant power P_load:

    V(t) = sqrt(V0² − 2·P_load·t / C)                  [discharging]

Charge/discharge time between voltage levels V_a and V_b:

    t = C · (V_b² − V_a²) / (2 · P)

Usable energy:
    E_usable = 0.5 · C · (V_max² − V_min²)             [J]

All time quantities in seconds, energy in Joules, power in Watts.
Functions also accept mW inputs via _mw variants or explicit unit parameters.

System load breakdown (SCD41 + ESP32-C3 at 3.3 V)
---------------------------------------------------
  SCD41 single-shot measurement: ~3.3 mA for 5 s  → 16.5 mC / measurement
  SCD41 standby leakage: ~40 µA
  ESP32-C3 deep sleep: ~5 µA
  ESP32-C3 active (BLE TX): ~80 mA for ~0.2 s per session

  Duty-cycled system (one measurement + BLE TX every T_period seconds):
    Q_meas  = 3.3e-3 A × 5 s       = 16.5 mC
    Q_tx    = 80e-3 A × 0.2 s      = 16.0 mC
    Q_sleep = 45e-6 A × T_period   [mC]
    I_avg   = (Q_meas + Q_tx + Q_sleep) / T_period
    P_avg   = I_avg × 3.3 V
"""

import numpy as np


# ---------------------------------------------------------------------------
# Default supercapacitor parameters
# ---------------------------------------------------------------------------
DEFAULT_SUPERCAP = {
    "C_sc":  1.0,    # capacitance [F]
    "V_max": 2.7,    # maximum rated voltage [V]
    "V_min": 1.0,    # minimum operational voltage [V]  (BQ25570 cold-start floor)
    "ESR":   0.05,   # equivalent series resistance [Ω]
}

# System load components at 3.3 V (duty-cycled)
SYSTEM_LOAD = {
    # SCD41 CO₂ sensor
    "I_scd41_active_A":  3.3e-3,   # current during single-shot measurement [A]
    "t_scd41_meas_s":    5.0,      # measurement duration [s]
    "I_scd41_idle_A":    40e-6,    # standby leakage [A]
    # ESP32-C3 microcontroller
    "I_mcu_sleep_A":     5e-6,     # deep-sleep current [A]
    "I_mcu_active_A":    80e-3,    # BLE TX active current [A]
    "t_mcu_active_s":    0.2,      # BLE TX duration per wake [s]
    # Supply rail
    "V_sys":             3.3,      # system supply voltage [V]
}

# System budget from Module 1
P_MIN_MW = 0.5   # minimum required TEG → boost output [mW]


# ---------------------------------------------------------------------------
# Energy & capacity helpers
# ---------------------------------------------------------------------------

def usable_energy(C_sc, V_max=2.7, V_min=1.0):
    """
    Energy available in the supercapacitor between V_max and V_min.

        E = 0.5 · C · (V_max² − V_min²)

    Parameters
    ----------
    C_sc  : float  Capacitance [F]
    V_max : float  Maximum voltage [V]
    V_min : float  Minimum operational voltage [V]

    Returns
    -------
    E_J   : float  Usable energy [J]
    """
    return 0.5 * C_sc * (V_max**2 - V_min**2)


def min_capacitance(E_J_required, V_max=2.7, V_min=1.0):
    """
    Minimum capacitance to store a given amount of usable energy.

        C_min = 2·E / (V_max² − V_min²)

    Parameters
    ----------
    E_J_required : float  Required usable energy [J]
    V_max, V_min : float  Voltage limits [V]

    Returns
    -------
    C_min : float  Minimum capacitance [F]
    """
    return 2.0 * E_J_required / (V_max**2 - V_min**2)


# ---------------------------------------------------------------------------
# Charge / discharge time
# ---------------------------------------------------------------------------

def charge_time(C_sc, P_in_W, V_start, V_end, ESR=0.0):
    """
    Time to charge the supercapacitor from V_start to V_end at constant
    power P_in (ideal constant-power source, e.g. MPPT or boost converter).

        t = C · (V_end² − V_start²) / (2 · P_in_eff)

    ESR losses reduce effective charging power at the capacitor terminals.
    For small ESR (ESR·I << V), the correction is minor; we apply a first-order
    correction assuming average current I_avg = P_in / V_avg.

    Parameters
    ----------
    C_sc    : float  Capacitance [F]
    P_in_W  : float  Input power from boost converter [W]
    V_start : float  Starting voltage [V]
    V_end   : float  Target voltage [V]
    ESR     : float  Equivalent series resistance [Ω]

    Returns
    -------
    t_s : float  Charge time [s]  (inf if P_in = 0)
    """
    if P_in_W <= 0 or V_end <= V_start:
        return np.inf
    V_avg = 0.5 * (V_start + V_end)
    I_avg = P_in_W / V_avg
    P_eff = P_in_W - I_avg**2 * ESR    # subtract ESR dissipation
    P_eff = max(P_eff, 1e-12)
    return C_sc * (V_end**2 - V_start**2) / (2.0 * P_eff)


def discharge_time(C_sc, P_load_W, V_start, V_end, ESR=0.0):
    """
    Time to discharge the supercapacitor from V_start to V_end at constant
    load power P_load.

        t = C · (V_start² − V_end²) / (2 · P_load_eff)

    Parameters
    ----------
    C_sc     : float  Capacitance [F]
    P_load_W : float  Load power [W]
    V_start  : float  Starting voltage [V]
    V_end    : float  Minimum voltage (cutoff) [V]
    ESR      : float  Equivalent series resistance [Ω]

    Returns
    -------
    t_s : float  Discharge time [s]
    """
    if P_load_W <= 0 or V_start <= V_end:
        return 0.0
    V_avg = 0.5 * (V_start + V_end)
    I_avg = P_load_W / V_avg
    P_eff = P_load_W + I_avg**2 * ESR   # ESR adds to effective drain
    return C_sc * (V_start**2 - V_end**2) / (2.0 * P_eff)


# ---------------------------------------------------------------------------
# Voltage vs. time trajectories
# ---------------------------------------------------------------------------

def voltage_vs_time_charge(C_sc, P_in_W, V_start, t_array, ESR=0.0):
    """
    Supercapacitor voltage during constant-power charging.

        V(t) = sqrt(V_start² + 2·P_in_eff·t / C)

    Clipped at V_max = 2.7 V (over-voltage protection assumed).

    Parameters
    ----------
    C_sc    : float    Capacitance [F]
    P_in_W  : float    Charging power [W]
    V_start : float    Initial voltage [V]
    t_array : ndarray  Time points [s]
    ESR     : float    Equivalent series resistance [Ω]

    Returns
    -------
    V : ndarray  Voltage at each time point [V]
    """
    t = np.asarray(t_array, dtype=float)
    V_avg_est = 0.5 * (V_start + 2.7)
    I_avg_est = P_in_W / max(V_avg_est, 1e-6)
    P_eff = max(P_in_W - I_avg_est**2 * ESR, 0.0)
    V_sq = V_start**2 + 2.0 * P_eff * t / C_sc
    V_sq = np.maximum(V_sq, 0.0)
    return np.minimum(np.sqrt(V_sq), 2.7)


def voltage_vs_time_discharge(C_sc, P_load_W, V_start, t_array, ESR=0.0):
    """
    Supercapacitor voltage during constant-power discharging.

        V(t) = sqrt(max(V_start² − 2·P_load_eff·t / C, 0))

    Parameters
    ----------
    C_sc     : float    Capacitance [F]
    P_load_W : float    Load power [W]
    V_start  : float    Initial voltage [V]
    t_array  : ndarray  Time points [s]
    ESR      : float    Equivalent series resistance [Ω]

    Returns
    -------
    V : ndarray  Voltage at each time point [V]
    """
    t = np.asarray(t_array, dtype=float)
    V_avg_est = 0.5 * (V_start + 1.0)
    I_avg_est = P_load_W / max(V_avg_est, 1e-6)
    P_eff = P_load_W + I_avg_est**2 * ESR
    V_sq = V_start**2 - 2.0 * P_eff * t / C_sc
    V_sq = np.maximum(V_sq, 0.0)
    return np.sqrt(V_sq)


# ---------------------------------------------------------------------------
# System power budget
# ---------------------------------------------------------------------------

def system_power_W(T_period_s, I_scd41_active_A=3.3e-3, t_scd41_meas_s=5.0,
                   I_scd41_idle_A=40e-6, I_mcu_sleep_A=5e-6,
                   I_mcu_active_A=80e-3, t_mcu_active_s=0.2,
                   V_sys=3.3):
    """
    Average system power consumption for one measurement + BLE TX cycle.

    Timeline per period T_period:
      [measurement: t_scd41_meas_s]  →  [BLE TX: t_mcu_active_s]  →  [sleep: remainder]

    Current draw:
      - During measurement: I_scd41_active + I_mcu_sleep (MCU just wakes to read)
      - During BLE TX: I_mcu_active + I_scd41_idle
      - During sleep: I_scd41_idle + I_mcu_sleep

    Parameters
    ----------
    T_period_s  : float  Measurement period (seconds between CO₂ readings)
    (other params from SYSTEM_LOAD defaults)

    Returns
    -------
    P_avg_W : float  Average system power [W]
    """
    t_meas  = min(t_scd41_meas_s, T_period_s)
    t_tx    = min(t_mcu_active_s, T_period_s - t_meas)
    t_sleep = max(T_period_s - t_meas - t_tx, 0.0)

    I_during_meas  = I_scd41_active_A + I_mcu_sleep_A
    I_during_tx    = I_mcu_active_A   + I_scd41_idle_A
    I_during_sleep = I_scd41_idle_A   + I_mcu_sleep_A

    Q_per_period = (I_during_meas  * t_meas  +
                    I_during_tx    * t_tx    +
                    I_during_sleep * t_sleep)

    I_avg = Q_per_period / T_period_s
    return I_avg * V_sys


def min_period_for_power(P_in_W, V_sys=3.3, **kwargs):
    """
    Minimum measurement period such that average system power ≤ P_in.

    Searches T_period from 10 s to 3600 s.

    Parameters
    ----------
    P_in_W : float  Available input power [W]

    Returns
    -------
    T_min_s : float  Minimum sustainable period [s], or inf if not possible
    """
    for t in range(10, 3601):
        if system_power_W(t, **kwargs) <= P_in_W:
            return float(t)
    return np.inf


# ---------------------------------------------------------------------------
# Full charge/discharge simulation
# ---------------------------------------------------------------------------

def simulate(C_sc, P_in_W, P_load_W, V_start=1.0, V_max=2.7, V_min=1.0,
             ESR=0.0, dt_s=0.1, t_max_s=3600.0):
    """
    Time-domain simulation of supercapacitor charging and discharging.

    Modes:
      - Net input  (P_in > P_load): capacitor charges
      - Net drain  (P_in < P_load): capacitor discharges
      - Equilibrium (P_in ≈ P_load): voltage holds steady

    Uses simple Euler integration with time step dt_s.

    Parameters
    ----------
    C_sc     : float  Capacitance [F]
    P_in_W   : float  Input power from TEG boost [W]
    P_load_W : float  Average system load power [W]
    V_start  : float  Initial voltage [V]
    V_max    : float  Maximum voltage (clamp) [V]
    V_min    : float  Minimum voltage (cutoff) [V]
    ESR      : float  Series resistance [Ω]
    dt_s     : float  Time step [s]
    t_max_s  : float  Total simulation duration [s]

    Returns
    -------
    dict with arrays:
        't'    : time [s]
        'V'    : capacitor voltage [V]
        'P_net': net charging power (P_in - P_load - P_ESR) [W]
        'E'    : stored energy [J]
        'SoC'  : state of charge [0–1] between V_min and V_max
    """
    n_steps = int(t_max_s / dt_s) + 1
    t_arr   = np.zeros(n_steps)
    V_arr   = np.zeros(n_steps)
    P_arr   = np.zeros(n_steps)
    E_arr   = np.zeros(n_steps)
    SoC_arr = np.zeros(n_steps)

    V = float(V_start)
    E_usable_total = usable_energy(C_sc, V_max, V_min)

    for i in range(n_steps):
        t_arr[i] = i * dt_s
        V_arr[i] = V
        E_stored = 0.5 * C_sc * max(V**2 - V_min**2, 0.0)
        E_arr[i]   = E_stored
        SoC_arr[i] = E_stored / E_usable_total if E_usable_total > 0 else 0.0

        # Net current at this voltage
        I_net = (P_in_W - P_load_W) / max(V, 1e-6)
        I_ESR = abs(I_net)
        P_ESR = I_ESR**2 * ESR
        P_net = P_in_W - P_load_W - P_ESR
        P_arr[i] = P_net

        # Euler step: C·dV = I_net·dt  →  dV = I_net·dt/C
        dV = I_net * dt_s / C_sc
        V = V + dV

        # Clamp
        if V >= V_max:
            V = V_max
        elif V <= V_min:
            V = V_min

    return {"t": t_arr, "V": V_arr, "P_net": P_arr,
            "E": E_arr, "SoC": SoC_arr}


# ---------------------------------------------------------------------------
# Duty-cycle analysis
# ---------------------------------------------------------------------------

def duty_cycle_analysis(P_in_W_values, T_period_candidates=None,
                        C_sc=1.0, V_max=2.7, V_min=1.0, ESR=0.05):
    """
    For each TEG input power level, find the minimum measurement period that
    keeps the system energy-neutral (P_load ≤ P_in) and compute key metrics.

    Parameters
    ----------
    P_in_W_values       : array-like  TEG boost output powers to evaluate [W]
    T_period_candidates : array-like  Periods to test [s] (default: 30–600 s)
    C_sc, V_max, V_min, ESR : supercap parameters

    Returns
    -------
    dict with lists (one entry per P_in value):
        'P_in_mW'      : input power [mW]
        'T_min_s'      : min sustainable period [s]
        'P_load_mW'    : average load at T_min [mW]
        'E_usable_mJ'  : usable energy in supercap [mJ]
        't_charge_s'   : charge time from V_min to V_max [s]
        't_discharge_s': discharge time from V_max to V_min at P_load [s]
    """
    if T_period_candidates is None:
        T_period_candidates = np.concatenate([
            np.arange(10, 60, 5),
            np.arange(60, 300, 10),
            np.arange(300, 3601, 60),
        ])

    E_use  = usable_energy(C_sc, V_max, V_min)
    result = {k: [] for k in ['P_in_mW', 'T_min_s', 'P_load_mW',
                               'E_usable_mJ', 't_charge_s', 't_discharge_s']}

    for P_in in np.asarray(P_in_W_values, dtype=float):
        T_min = np.inf
        P_at_T = 0.0
        for T in T_period_candidates:
            P_sys = system_power_W(T)
            if P_sys <= P_in:
                T_min  = float(T)
                P_at_T = P_sys
                break

        t_ch = charge_time(C_sc, P_in, V_min, V_max, ESR) if P_in > 0 else np.inf
        t_dis = (discharge_time(C_sc, P_at_T, V_max, V_min, ESR)
                 if P_at_T > 0 else np.inf)

        result['P_in_mW'].append(P_in * 1e3)
        result['T_min_s'].append(T_min)
        result['P_load_mW'].append(P_at_T * 1e3)
        result['E_usable_mJ'].append(E_use * 1e3)
        result['t_charge_s'].append(t_ch)
        result['t_discharge_s'].append(t_dis)

    return result
