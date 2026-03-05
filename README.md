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
├── 03_CO2_Room_Model.ipynb         ← Module 3 (complete)
├── 04_Fatigue_Model.ipynb          ← Module 4 (complete)
├── 05_Wokwi_Firmware/              ← Module 5 (complete)
│   ├── ghostbreath.ino             ← ESP32 Arduino sketch
│   ├── diagram.json                ← Wokwi circuit schematic
│   └── README.md                   ← Simulation instructions
├── 06_Full_System_Simulator.ipynb  ← Module 6 (upcoming)
├── utils/
│   ├── __init__.py
│   ├── teg_model.py                ← TEG physics functions
│   ├── supercap_model.py           ← Supercapacitor energy buffer model
│   ├── co2_model.py                ← CO₂ room mass-balance ODE model
│   └── fatigue_model.py            ← Fatigue risk scoring model
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
| 3 | CO₂ Room Buildup Model | ✅ Complete |
| 4 | Cognitive Fatigue Risk Model | ✅ Complete |
| 5 | MCU Firmware Simulation (Wokwi) | ✅ Complete |
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

**Key result:** GhostBreath is feasible for ΔT_source ≥ 6 °C (worst-case 40% thermal coupling).
Laptop exhaust provides ΔT_source = 10–25 °C. Even under the most conservative clip-on coupling
(40%), the device produces 1.72 mW at ΔT = 10 °C and 10.75 mW at ΔT = 25 °C — 3.4–21.5× the
0.5 mW system power budget. At nominal 50% coupling: 2.69–16.80 mW across the operating range.

| ΔT_source | Ideal P_boost (η=100%) | Realistic mid (50%) | Realistic low (40%) |
|-----------|------------------------|---------------------|---------------------|
| 10 °C | 10.75 mW | 2.69 mW | 1.72 mW ✓ |
| 15 °C | 24.19 mW | 6.05 mW | 3.87 mW ✓ |
| 20 °C | 43.01 mW | 10.75 mW | 6.88 mW ✓ |
| 25 °C | 67.20 mW | 16.80 mW | 10.75 mW ✓ |

**Figures generated:**
- `figures/01a_teg_voltage_power_current.png` — 3-panel voltage, power, current sweep
- `figures/01b_teg_feasibility.png` — Feasibility plot with 0.5 mW budget line
- `figures/01c_teg_heatsink_analysis.png` — Heatsink thermal resistance impact
- `figures/01d_teg_iv_pv_curves.png` — I-V and P-V characteristics
- `figures/01e_teg_realistic_power.png` — Realistic power band with thermal coupling losses (40–60% efficiency)

---

## Module 2: Supercapacitor Energy Buffer

**Device:** 1 F EDLC (e.g. Murata JUWT1105MCD)

| Parameter | Symbol | Value |
|-----------|--------|-------|
| Capacitance | C | 1 F |
| Max voltage | V_max | 2.7 V |
| Min voltage | V_min | 1.0 V |
| ESR | R_ESR | 50 mΩ |
| Usable energy | E | ≈ 3.14 J |

**System load (SCD41 + ESP32-C3, duty-cycled at 3.3 V):**

| Phase | Current | Duration |
|-------|---------|----------|
| CO₂ measurement (SCD41) | 3.3 mA | 5 s |
| BLE transmit (ESP32-C3) | 80 mA | 0.2 s |
| Deep sleep (both) | ~45 µA | remainder |

**Key results:**
- Minimum sustainable measurement period: 68 s worst-case (ΔT=10 °C, 40% coupling); 19 s nominal (ΔT=15 °C, 50%)
- Cold-start boot time (V_min → 1.5 V): < 5 min at all viable ΔT levels
- Discharge survival with TEG off: > 5 min at T = 120 s duty cycle
- 1 F supercap provides ~29× safety margin over minimum required capacitance

**Figures generated:**
- `figures/02a_supercap_load_vs_period.png` — System load vs. measurement period with TEG power lines
- `figures/02b_supercap_charge_time.png` — Charge time vs. input power and voltage trajectories
- `figures/02c_supercap_energy_budget.png` — Energy budget breakdown and minimum capacitance
- `figures/02d_supercap_simulation.png` — Time-domain voltage simulation (charge + operate)
- `figures/02e_supercap_discharge.png` — Discharge-only scenario (TEG off survivability)

---

## Module 3: CO₂ Room Buildup Model

**Physics:** Well-mixed room mass-balance ODE with time-varying ventilation events.

| Parameter | Symbol | Value |
|-----------|--------|-------|
| Room volume | V | 27 m³ (3×3×3 m hostel room) |
| Baseline ACH | ACH | 0.3 h⁻¹ (windows closed) |
| Outdoor CO₂ | C_ambient | 420 ppm |
| Human production (light study) | Q | 5 mL/s (300 mL/min) |
| Window-open ACH | ACH_open | 3.0 h⁻¹ |

**Impairment thresholds:**

| CO₂ Level | Effect |
|-----------|--------|
| 1000 ppm | Mild cognitive impairment |
| 1500 ppm | Significant impairment |
| 2500 ppm | Severe impairment |

**Key results:**
- Reference room hits 1000 ppm in ~58 min, 1500 ppm in ~117 min
- Steady-state CO₂ ≈ 2642 ppm (well above danger threshold for ACH=0.3)
- Opening a window for 10 min (ACH→3.0) drops CO₂ by ~200–400 ppm
- 2-person room crosses 1000 ppm in ~30 min; 3-person in ~20 min
- Max numerical error vs analytical: < 0.001 ppm ✓

**Figures generated:**
- `figures/03a_co2_timeseries.png` — CO₂ vs time with threshold zones + dC/dt rate panel
- `figures/03b_co2_ventilation_events.png` — Ventilation events (1×, 2× window opening)
- `figures/03c_co2_heatmap.png` — 2D heatmap: time-to-threshold vs room size × ACH
- `figures/03d_co2_scenarios.png` — Multiple occupancy & metabolic rate comparisons

---

## Module 4: Cognitive Fatigue Risk Model

**Model:** Weighted sigmoid — 3 inputs, 1 output (score 0–1). Lightweight enough
for ESP32-C3 integer arithmetic (3 multiplies + 2 exp() calls per sample).

| Input | Symbol | Source |
|-------|--------|--------|
| CO₂ concentration | C [ppm] | SCD41 reading (Module 2/3) |
| CO₂ rate of change | dC/dt [ppm/min] | Finite difference on readings |
| Study duration | t [min] | System clock |

**Scoring formula:**

`score = 0.60 · f_co₂(C) + 0.20 · f_rate(dC/dt) + 0.20 · f_time(t)`

| Score | Classification | CO₂ context |
|-------|---------------|-------------|
| 0.00 – 0.30 | Safe | typically < 1000 ppm |
| 0.30 – 0.60 | Mild Fatigue | typically 1000–1500 ppm |
| 0.60 – 1.00 | High Fatigue | typically > 1400 ppm or long session |

**Key results (1 person, 27 m³ room, windows closed):**
- Mild Fatigue alert at **t ≈ 45 min** (C ≈ 868 ppm) — 16 min earlier than fixed CO₂ threshold
- High Fatigue alert at **t ≈ 103 min** (C ≈ 1314 ppm) — 31 min earlier than 1500 ppm threshold
- Opening a window at t = 90 min delays High Fatigue alert by > 60 min
- Two occupants triggers High Fatigue alert 2.5× sooner (t ≈ 48 min)
- Model adds **zero additional energy cost** (runs inside existing BLE TX wake window)

**Figures generated:**
- `figures/04a_fatigue_score_vs_time.png` — CO₂ and fatigue score dual-panel, 4-hour session
- `figures/04b_alert_thresholds.png` — Score decomposition + decision surface contour map
- `figures/04c_scenario_comparison.png` — Three scenarios: window closed / open / 2 occupants

---

## Module 5: Embedded Firmware Simulation (Wokwi)

**Platform:** ESP32 DevKit v1 simulated in [Wokwi](https://wokwi.com)
**Folder:** `05_Wokwi_Firmware/`

The firmware is a **direct C port** of the Python fatigue model from Module 4.
Every constant and formula is identical — only the input source changes (ADC
potentiometers replace the CO₂ ODE solver).

### Circuit

| Component | GPIO | Role |
|-----------|------|------|
| Left potentiometer | 34 (ADC) | CO₂ concentration: 420–2500 ppm |
| Right potentiometer | 35 (ADC) | TEG boost voltage: 0–3.3 V |
| Red LED | 2 | Fatigue alert indicator |
| Buzzer | 4 | Fatigue alert tone |

### Firmware duty cycle

```
Wake → Read CO₂ ADC → Read TEG ADC → Compute dC/dt
     → score = 0.60·f_co2 + 0.20·f_rate + 0.20·f_time
     → If score ≥ 0.70: LED ON + Buzzer ON
     → Serial log → Deep sleep 5 min  (delay 5 s in Wokwi)
```

### Firmware–Model consistency

All sigmoid parameters match `utils/fatigue_model.py` exactly:

| Constant | Python | C |
|----------|--------|---|
| CO₂ sigmoid centre | `_CO2_CENTRE = 1250.0` | `CO2_CENTRE 1250.0f` |
| CO₂ sigmoid scale | `_CO2_SCALE = 0.0040` | `CO2_SCALE 0.004f` |
| Time sigmoid centre | `_TIME_CENTRE = 90.0` | `TIME_CENTRE 90.0f` |
| Time sigmoid scale | `_TIME_SCALE = 0.033` | `TIME_SCALE 0.033f` |
| Rate clamp | `_RATE_MAX = 15.0` | `RATE_MAX 15.0f` |
| Weights | 0.60 / 0.20 / 0.20 | 0.60f / 0.20f / 0.20f |

### How to run

1. Go to **[wokwi.com](https://wokwi.com)** → New Project → ESP32
2. Paste `ghostbreath.ino` into the sketch editor
3. Click the `diagram.json` tab and paste `diagram.json`
4. Press ▶ **Start Simulation** — open the Serial Monitor at 115200 baud
5. Turn the left potentiometer clockwise to raise CO₂ and watch the LED

See `05_Wokwi_Firmware/README.md` for detailed instructions, expected serial
output, and the four screenshots required for the project report.

### Serial output sample

```
+---------------------------------------------------------+
|  GhostBreath   Cycle #006      Session:    30 min       |
+-----------------------------+---------------------------+
|  CO2    :  1900.0 ppm       |  dC/dt :  +296.00 ppm/min |
|  TEG    :   2.100 V          |  Score :  0.7614          |
|  Status : ALERT / HIGH FATIGUE |  Alert :  ON          |
+---------------------------------------------------------+
```

---

## References
- Sadat-Mohammadi et al. (2017). *Energy harvesting from laptop exhaust using TEGs.*
- TEC1-12706 datasheet — Hebei I.T. Shanghai Co.
- Du et al. (2020). *Indoor CO₂ and cognitive performance.*
- Zhang et al. (2023). *CO₂ concentration and occupant comfort.*
- Harvard CogFx Study — Allen et al. (2016).
- Prickett & Davis (2019). *Supercapacitor energy storage for IoT edge devices.*
