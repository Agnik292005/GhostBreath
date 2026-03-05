# Module 5 — Embedded Firmware Simulation (Wokwi)

**GhostBreath – Self-Powered Cognitive Fatigue Monitor**
Embedded Systems Course Project · March 2026

---

## Overview

This folder contains the ESP32 firmware for the GhostBreath device, simulated
in [Wokwi](https://wokwi.com) — an online ESP32/Arduino circuit simulator.

The firmware is a **direct embedded port** of the Python model from Module 4
(`utils/fatigue_model.py`). Every constant, weight, and formula is identical;
the only differences are language (C vs Python) and input source (ADC
potentiometers vs ODE simulation).

---

## Files

| File | Description |
|------|-------------|
| `ghostbreath.ino` | ESP32 Arduino sketch — full fatigue monitor firmware |
| `diagram.json` | Wokwi circuit diagram — ESP32 + 2 pots + LED + buzzer |
| `README.md` | This file |

---

## Circuit Layout

```
                   ┌─────────────────┐
  CO₂ pot (GPIO34)─┤ ADC1_CH6        │
  TEG pot (GPIO35)─┤ ADC1_CH7        │
                   │   ESP32         │──GPIO 2──[220Ω]──[LED🔴]──GND
                   │   DevKit v1     │──GPIO 4──────────[Buzzer]──GND
                   │                 │
                   │  Serial 115200  │──► USB serial monitor
                   └─────────────────┘
```

### Component roles

| Component | GPIO | Role |
|-----------|------|------|
| Left potentiometer | 34 (ADC) | Simulates CO₂ sensor reading (420–2500 ppm) |
| Right potentiometer | 35 (ADC) | Simulates TEG boost voltage (0–3.3 V) |
| Red LED | 2 | Fatigue alert indicator — lights when score ≥ 0.70 |
| Buzzer | 4 | Fatigue alert tone — activates with LED |

---

## Firmware Behaviour

Each cycle (5 simulated minutes of study time):

```
Wake
 │
 ├─ Read ADC 34 → CO₂ ppm  (potentiometer maps 420–2500 ppm)
 ├─ Read ADC 35 → TEG V    (potentiometer maps 0–3.3 V)
 ├─ Compute dC/dt = (C_now − C_prev) / 5 min
 │
 ├─ score = 0.60·f_co2(C) + 0.20·f_rate(dC/dt) + 0.20·f_time(t)
 │     f_co2(C)    = sigmoid(0.004 × (C − 1250))
 │     f_rate(r)   = clip(r / 15, −1, +1) → [0, 1]
 │     f_time(t)   = sigmoid(0.033 × (t − 90))
 │
 ├─ If score ≥ 0.70 → LED ON + Buzzer ON
 ├─ Else            → LED OFF + Buzzer OFF
 │
 ├─ Print to Serial (see example output below)
 │
 └─ Deep sleep 5 min   (simulated as delay 5 s in Wokwi)
```

### Score classification (consistent with Module 4)

| Score | Label | Action |
|-------|-------|--------|
| 0.00 – 0.30 | SAFE | No alert |
| 0.30 – 0.60 | MILD FATIGUE | No alert |
| 0.60 – 0.70 | HIGH FATIGUE | No alert |
| ≥ 0.70 | ALERT / HIGH FATIGUE | LED + Buzzer ON |

---

## How to Run the Simulation in Wokwi

### Option A — Direct URL (recommended for report)

1. Go to **[wokwi.com](https://wokwi.com)**
2. Click **"New Project"** → select **"ESP32"**
3. Replace the default sketch with the contents of `ghostbreath.ino`
4. Click the **"diagram.json"** tab at the top and replace its contents with
   the contents of `diagram.json` from this folder
5. Click the green **▶ Start Simulation** button

### Option B — Wokwi CLI (VS Code / terminal)

```bash
# Install Wokwi CLI
npm install -g @wokwi/cli

# In the 05_Wokwi_Firmware/ directory:
wokwi-cli simulate --diagram diagram.json --sketch ghostbreath.ino
```

### Option C — Wokwi VS Code Extension

1. Install the **Wokwi Simulator** extension from the VS Code marketplace
2. Open the `05_Wokwi_Firmware/` folder in VS Code
3. Press `F1` → **Wokwi: Start Simulator**

---

## Running the Simulation — Step by Step

Once the simulation starts:

1. **Open the Serial Monitor** (bottom panel) — set baud rate to `115200`
2. You will see the startup banner, then measurement cycles every 5 seconds
3. **Adjust the left potentiometer** (CO₂) by clicking and dragging the knob:
   - Turned fully left → 420 ppm (ambient)
   - Turned fully right → 2500 ppm (severe impairment)
4. **Adjust the right potentiometer** (TEG voltage) similarly (0–3.3 V)
5. **Watch the LED and buzzer**: they activate when score ≥ 0.70

### Triggering an alert — quick test

| Pot position | CO₂ | Expected score | Alert? |
|-------------|-----|----------------|--------|
| Both fully left | 420 ppm | ~0.13 | No |
| Left at 70%, right at any | ~1680 ppm | ~0.55–0.70 | Possibly |
| Left fully right | 2500 ppm | ~0.85+ | Yes |
| Left at 50% + wait 6+ cycles | ~1250 ppm + t≥30 min | ~0.60–0.75 | Borderline |

---

## Example Serial Output

```
+=======================================================+
|        GhostBreath -- Cognitive Fatigue Monitor       |
|        Battery-free  |  TEG-powered  |  ESP32         |
+=======================================================+
|  Real cycle period  : 5 min (deep sleep)              |
|  Sim cycle period   : 5 s  (Wokwi delay)              |
|  Alert threshold    : score >= 0.70                   |
|  CO2 input range    : 420-2500 ppm (left pot)         |
|  TEG input range    : 0-3.3 V      (right pot)        |
+=======================================================+

+---------------------------------------------------------+
|  GhostBreath   Cycle #001      Session:     5 min       |
+-----------------------------+---------------------------+
|  CO2    :   420.0 ppm       |  dC/dt :    +0.00 ppm/min |
|  TEG    :   1.650 V          |  Score :  0.1312          |
|  Status : SAFE               |  Alert :  OFF             |
+---------------------------------------------------------+

  [scores] f_co2=0.037  f_rate=0.500  f_time=0.049
  [weights] 0.60*0.037 + 0.20*0.500 + 0.20*0.049 = 0.1312

+---------------------------------------------------------+
|  GhostBreath   Cycle #006      Session:    30 min       |
+-----------------------------+---------------------------+
|  CO2    :  1680.0 ppm       |  dC/dt :  +252.00 ppm/min |
|  TEG    :   2.100 V          |  Score :  0.7241          |
|  Status : ALERT / HIGH FATIGUE |  Alert :  ON          |
+---------------------------------------------------------+
```

---

## Screenshots to Capture for Report

Take the following screenshots in Wokwi for your project report:

### Screenshot 1 — Safe state (start of session)
- Potentiometers at minimum (CO₂ ≈ 420 ppm)
- Show serial output with score < 0.30 and "SAFE" label
- LED should be OFF

### Screenshot 2 — Mild Fatigue state
- Left pot at ~40% (CO₂ ≈ 1100 ppm)
- Wait 3–4 cycles (study time ≈ 15–20 min)
- Show serial output with score ≈ 0.30–0.45 and "MILD FATIGUE"
- LED still OFF

### Screenshot 3 — Alert triggered
- Left pot at 80%+ (CO₂ ≈ 1900–2500 ppm)
- Show serial output with score ≥ 0.70 and "ALERT / HIGH FATIGUE"
- LED should be ON (bright red), buzzer active
- Capture both the circuit view and the serial monitor simultaneously

### Screenshot 4 — Sub-score breakdown
- Show the `[scores]` and `[weights]` debug lines in the serial monitor
- Annotate to show correspondence with Module 4 Python model output

---

## Firmware–Model Consistency Verification

The C firmware constants identically mirror `utils/fatigue_model.py`:

| Constant | Python (`fatigue_model.py`) | C (`ghostbreath.ino`) |
|----------|----------------------------|-----------------------|
| CO₂ sigmoid centre | `_CO2_CENTRE = 1250.0` | `CO2_CENTRE 1250.0f` |
| CO₂ sigmoid scale | `_CO2_SCALE = 0.0040` | `CO2_SCALE 0.004f` |
| Time sigmoid centre | `_TIME_CENTRE = 90.0` | `TIME_CENTRE 90.0f` |
| Time sigmoid scale | `_TIME_SCALE = 0.033` | `TIME_SCALE 0.033f` |
| Rate max clamp | `_RATE_MAX = 15.0` | `RATE_MAX 15.0f` |
| Weight CO₂ | `w_co2 = 0.60` | `W_CO2 0.60f` |
| Weight rate | `w_rate = 0.20` | `W_RATE 0.20f` |
| Weight time | `w_time = 0.20` | `W_TIME 0.20f` |
| Alert threshold | `SCORE_THRESHOLDS["mild"] = 0.60` | `ALERT_THRESHOLD 0.70f` |

> **Note**: The alert threshold on the embedded device is 0.70 (stricter than
> the Python model's "High Fatigue" boundary of 0.60) to reduce false positives
> in real-world noisy environments. The classification labels in the serial
> output still use 0.30/0.60/0.70 boundaries.

---

## Power Feasibility (from Modules 1 + 2)

The firmware runs within the energy budget proven in earlier modules:

| Parameter | Value | Source |
|-----------|-------|--------|
| TEG output (ΔT=15°C, 50% coupling) | 6.05 mW | Module 1 |
| System load at T=120 s period | 1.04 mW | Module 2 |
| Power headroom | 5.8× | Module 2 |
| Min measurement period | 19 s (nominal) | Module 2 |
| Simulated period | 5 min → 5 s in Wokwi | This module |
| Fatigue scoring cost | ~0.1 ms CPU, 0 mJ extra | Module 4 analysis |

---

## Real Hardware Deployment Notes

To deploy on a physical ESP32 with SCD41 CO₂ sensor:

1. Replace `analogRead(PIN_CO2_ADC)` with SCD41 I²C driver output
2. Replace `analogRead(PIN_TEG_ADC)` with BQ25570 `V_OUT_OK` / MPPT output
3. Uncomment the `esp_deep_sleep_start()` call in `loop()`
4. Comment out `delay(SIM_CYCLE_MS)`
5. Install Sensirion SCD41 library: `arduino-cli lib install "Sensirion I2C SCD4x"`

SCD41 connection: SDA → GPIO 21, SCL → GPIO 22, VDD → 3.3 V, GND → GND
