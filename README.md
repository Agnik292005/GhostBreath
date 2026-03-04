# GhostBreath – Self-Powered Cognitive Fatigue Monitor
### Embedded Systems Course Project · March 2026

A battery-free, clip-on device concept that harvests laptop exhaust heat via a
thermoelectric generator (TEG) to power a CO₂ sensor and microcontroller.
Cognitive fatigue is predicted by correlating CO₂ levels, workload intensity
(inferred from TEG voltage), and session duration.

This repository contains the **full software simulation** — no physical hardware required.

---

## Repository Structure

```
GhostBreath/
├── 01_TEG_Power_Model.ipynb        ← Module 1 (complete)
├── 02_Supercap_Model.ipynb         ← Module 2 (complete)
├── 03_CO2_Room_Model.ipynb         ← Module 3 (upcoming)
├── 04_Fatigue_Prediction.ipynb     ← Module 4 (upcoming)
├── 05_Wokwi_Firmware/
│   ├── ghostbreath.ino             ← Module 5 (upcoming)
│   └── diagram.json
├── 06_Full_System_Simulator.ipynb  ← Module 6 (upcoming)
├── utils/
│   ├── __init__.py
│   ├── teg_model.py                ← TEG physics functions
│   ├── supercap_model.py           ← Supercapacitor energy buffer model
│   ├── co2_model.py                ← (upcoming)
│   └── fatigue_model.py            ← (upcoming)
├── models/
│   └── fatigue_model.tflite        ← (upcoming)
├── figures/
│   └── (all exported 300 DPI PNGs)
└── README.md
```

---

## Module Status

| Module | Description | Status |
|--------|-------------|--------|
| 1 | TEG Power Output vs. ΔT | ✅ Complete |
| 2 | Supercapacitor Charge/Discharge | ✅ Complete |
| 3 | CO₂ Room Buildup Model | 🔜 Upcoming |
| 4 | Cognitive Fatigue Prediction (ML) | 🔜 Upcoming |
| 5 | MCU Firmware Simulation (Wokwi) | 🔜 Upcoming |
| 6 | Full System Integration Simulator | 🔜 Upcoming |

---

## Quick Start

```bash
pip install jupyter numpy scipy matplotlib tensorflow
jupyter notebook
```

Open any notebook and **Run All Cells**. Each notebook is self-contained.

---

## Module 1: TEG Power Model

**Device:** TEC1-12706 Peltier module (used as TEG)

| Parameter | Value |
|-----------|-------|
| Thermocouple couples (N) | 127 |
| Seebeck coefficient (α) | 200 µV/K |
| Internal resistance (R_int) | 1.2 Ω |
| Thermal conductance (K_teg) | 0.5 W/K |
| Boost converter efficiency | 80% (BQ25570) |

**Key result:** GhostBreath is feasible for ΔT ≥ 8 °C. Laptop exhaust provides
ΔT = 10–25 °C, yielding P_boost = 0.5–5 mW against a 0.5 mW system budget.

**Figures generated:**
- `figures/01a_teg_voltage_power_current.png` — 3-panel voltage, power, current sweep
- `figures/01b_teg_feasibility.png` — Feasibility plot with 0.5 mW budget line
- `figures/01c_teg_heatsink_analysis.png` — Heatsink thermal resistance impact
- `figures/01d_teg_iv_pv_curves.png` — I-V and P-V characteristics

---

## Module 2: Supercapacitor Energy Buffer

**Device:** 1 F EDLC (e.g. Murata JUWT1105MCD)

| Parameter | Symbol | Value |
|-----------|--------|-------|
| Capacitance | C | 1 F |
| Max voltage | V_max | 2.7 V |
| Min voltage | V_min | 1.0 V |
| ESR | R_ESR | 50 mΩ |
| Usable energy | E | ≈ 3.14 mJ |

**System load (SCD41 + ESP32-C3, duty-cycled at 3.3 V):**

| Phase | Current | Duration |
|-------|---------|----------|
| CO₂ measurement (SCD41) | 3.3 mA | 5 s |
| BLE transmit (ESP32-C3) | 80 mA | 0.2 s |
| Deep sleep (both) | ~45 µA | remainder |

**Key results:**
- With ΔT_src = 15 °C and η_th = 50%: minimum sustainable measurement period is ~60–120 s
- Cold-start boot time (V_min → 1.5 V): < 5 min at all viable ΔT levels
- Discharge survival with TEG off: > 5 min at T = 120 s duty cycle
- 1 F supercap provides ~100× safety margin over minimum required capacitance

**Figures generated:**
- `figures/02a_supercap_load_vs_period.png` — System load vs. measurement period with TEG power lines
- `figures/02b_supercap_charge_time.png` — Charge time vs. input power and voltage trajectories
- `figures/02c_supercap_energy_budget.png` — Energy budget breakdown and minimum capacitance
- `figures/02d_supercap_simulation.png` — Time-domain voltage simulation (charge + operate)
- `figures/02e_supercap_discharge.png` — Discharge-only scenario (TEG off survivability)

---

## References
- Sadat-Mohammadi et al. (2017). *Energy harvesting from laptop exhaust using TEGs.*
- TEC1-12706 datasheet — Hebei I.T. Shanghai Co.
- Du et al. (2020). *Indoor CO₂ and cognitive performance.*
- Zhang et al. (2023). *CO₂ concentration and occupant comfort.*
- Harvard CogFx Study — Allen et al. (2016).
- Prickett & Davis (2019). *Supercapacitor energy storage for IoT edge devices.*
