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

**v2 adds:** SSD1306 OLED live display, three Wokwi bug-fixes.

---

## Files

| File | Description |
|------|-------------|
| `ghostbreath.ino` | ESP32 Arduino sketch — full fatigue monitor firmware (v2) |
| `diagram.json` | Wokwi circuit diagram — ESP32 + 2 pots + LED + buzzer + OLED |
| `wokwi.toml` | Library declarations for Wokwi (Adafruit GFX + SSD1306) |
| `README.md` | This file |

---

## Circuit Layout

```
                   ┌──────────────────────────────┐
  CO₂ pot (GPIO34)─┤ ADC1_CH6                     │
  TEG pot (GPIO35)─┤ ADC1_CH7                     │
                   │   ESP32                       │──GPIO 2──[220Ω]──[LED🔴]──GND
                   │   DevKit v1                   │──GPIO 4──────────[Buzzer]──GND
                   │                               │
                   │   GPIO21 (SDA) ───────────────┼──SDA──┐
                   │   GPIO22 (SCL) ───────────────┼──SCL──┤  SSD1306
                   │   3V3 ────────────────────────┼──VCC──┤  OLED 128×64
                   │   GND ────────────────────────┼──GND──┘
                   │                               │
                   │   Serial 115200               │──► USB serial (optional)
                   └──────────────────────────────┘
```

### Component roles

| Component | GPIO | Role |
|-----------|------|------|
| Left potentiometer | 34 (ADC) | Simulates CO₂ sensor reading (420–2500 ppm) |
| Right potentiometer | 35 (ADC) | Simulates TEG boost voltage (0–3.3 V) |
| Red LED | 2 | Fatigue alert indicator — lights when score ≥ 0.70 |
| Buzzer | 4 | Fatigue alert tone — 1 kHz via `tone()` |
| SSD1306 OLED 128×64 | 21 (SDA), 22 (SCL) | Live CO₂ / score / status display |

---

## Wokwi Bug-Fixes Applied in v2

| # | Root Cause | Symptom | Fix |
|---|-----------|---------|-----|
| 1 | `analogRead()` defaults to `ADC_0db` attenuation (0–1.1 V range); the 3.3 V pot signal maps to 0 in some Wokwi builds | CO₂ locks at 420 ppm; score never crosses 0.70; LED/buzzer never fire | `analogSetAttenuation(ADC_11db)` in `setup()` before any ADC call |
| 2 | `while (!Serial) delay(10)` deadlocks `setup()` on some Wokwi/ESP32-Arduino versions | Firmware hangs on boot; no cycles ever run | Removed the guard entirely |
| 3 | `wokwi-buzzer` requires a frequency-modulated signal; `digitalWrite(HIGH)` is silent in the simulator | Alert LED lights but buzzer makes no sound | Replaced with `tone(PIN_BUZZER, 1000)` / `noTone(PIN_BUZZER)` |

Additionally, the CO₂ potentiometer default `value` in `diagram.json` is now
`"0.75"` (≈ 1980 ppm) so the demo starts with elevated CO₂ and alerts fire
within 1–2 cycles without requiring manual adjustment.

---

## OLED Display

Each cycle the SSD1306 screen refreshes with four lines:

```
┌────────────────────────┐
│ GhostBreath            │  ← fixed title
│────────────────────────│
│ CO2: 1980 ppm          │  ← live ADC reading
│ Score: 0.752           │  ← fatigue risk score
│                        │
│ ██████████████████████ │  ← status (inverted white banner on ALERT)
│ █    ALERT           █ │
└────────────────────────┘
```

| Score range | OLED text (Line 4) | Font | Background |
|-------------|-------------------|------|------------|
| < 0.30 | `SAFE` | Size 1 (normal) | Black |
| 0.30 – 0.60 | `MILD FATIGUE` | Size 1 (normal) | Black |
| 0.60 – 0.70 | `HIGH FATIGUE` | Size 1 (normal) | Black |
| ≥ 0.70 | `ALERT` | Size 2 (large) | **White** (inverted, black text) |

---

## Library Setup (wokwi.toml)

The `wokwi.toml` file declares the required Adafruit libraries so Wokwi
installs them automatically before compiling:

```toml
[wokwi]
version = 1

[[libraries]]
name = "Adafruit SSD1306"
version = "*"

[[libraries]]
name = "Adafruit GFX Library"
version = "*"
```

When using the **Wokwi VS Code extension** or **Wokwi CLI**, place `wokwi.toml`
in the same folder as `ghostbreath.ino`. When using **wokwi.com** directly,
the libraries are auto-resolved from `#include` directives, so no extra step
is needed.

---

## Firmware Behaviour

Each cycle (5 simulated minutes of study time):

```
Wake
 │
 ├─ Read ADC 34 × 8 samples → CO₂ ppm  (potentiometer maps 420–2500 ppm)
 ├─ Read ADC 35 × 8 samples → TEG V    (potentiometer maps 0–3.3 V)
 ├─ Compute dC/dt = (C_now − C_prev) / 5 min
 │
 ├─ score = 0.60·f_co2(C) + 0.20·f_rate(dC/dt) + 0.20·f_time(t)
 │     f_co2(C)    = sigmoid(0.004 × (C − 1250))
 │     f_rate(r)   = clip(r / 15, −1, +1) → [0, 1]
 │     f_time(t)   = sigmoid(0.033 × (t − 90))
 │
 ├─ If score ≥ 0.70 → LED ON + tone(buzzer, 1 kHz) + OLED "ALERT" (inverted)
 ├─ Else            → LED OFF + noTone(buzzer)     + OLED status text
 │
 ├─ Serial: print cycle table + sub-score breakdown (optional)
 │
 └─ Deep sleep 5 min   (simulated as delay 5 s in Wokwi)
```

### Score classification (consistent with Module 4)

| Score | Label | Action |
|-------|-------|--------|
| 0.00 – 0.30 | SAFE | No alert |
| 0.30 – 0.60 | MILD FATIGUE | No alert |
| 0.60 – 0.70 | HIGH FATIGUE | No alert |
| ≥ 0.70 | ALERT | LED + Buzzer + OLED inverted banner |

---

## How to Run the Simulation in Wokwi

### Option A — Direct URL (recommended)

1. Go to **[wokwi.com](https://wokwi.com)**
2. Click **"New Project"** → select **"ESP32"**
3. Replace the default sketch with the contents of `ghostbreath.ino`
4. Click the **"diagram.json"** tab and replace its contents with `diagram.json`
5. Click the green **▶ Start Simulation** button
6. The OLED display appears on-screen immediately; no Serial Monitor needed

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

1. **Watch the OLED display** on-screen — it shows CO₂, score, and status
   without opening the Serial Monitor
2. The CO₂ pot starts at **75%** (≈ 1980 ppm) so the score begins elevated
3. **Within 1–2 cycles** (5–10 s real time) the score should cross 0.70:
   - OLED shows large **ALERT** in an inverted white banner
   - **Red LED** lights up
   - **Buzzer** sounds at 1 kHz
4. **Turn the CO₂ pot counter-clockwise** to lower CO₂ and watch the score drop
   back to SAFE — LED/buzzer deactivate, OLED returns to normal text
5. **Serial Monitor** (115200 baud) optionally shows the full per-cycle table
   and sub-score breakdown for verification

### Triggering an alert — quick reference

| Pot position (left/CO₂) | CO₂ equivalent | Score at cycle 1 | Alert? |
|--------------------------|---------------|-----------------|--------|
| Fully left (0%) | 420 ppm | ~0.13 | No |
| 50% | ~1460 ppm | ~0.63 | Not yet |
| 75% (default in diagram) | ~1980 ppm | ~0.81 | **Yes** |
| Fully right (100%) | 2500 ppm | ~0.85 | **Yes** |

> At 50% the score starts below 0.70 but rises above it after ~20 cycles
> (100 simulated minutes) as the `f_time` component increases.

---

## Example OLED Screens

**Safe state** (CO₂ pot at minimum):
```
GhostBreath
────────────────
CO2: 420 ppm
Score: 0.131

SAFE
```

**Alert state** (CO₂ pot at 75%+):
```
GhostBreath
────────────────
CO2: 1980 ppm
Score: 0.807

████████████████
█    ALERT     █  ← large white-on-black banner
████████████████
```

---

## Example Serial Output (optional, 115200 baud)

```
+=======================================================+
|       GhostBreath v2 -- Cognitive Fatigue Monitor     |
|   Battery-free  |  TEG-powered  |  ESP32 + OLED       |
+=======================================================+
...
Bug-fixes applied (v2):
  [1] analogSetAttenuation(ADC_11db) -- full 0-3.3V ADC range
  [2] Removed while(!Serial) guard  -- no Wokwi deadlock
  [3] tone()/noTone() buzzer         -- audible in Wokwi

+---------------------------------------------------------+
|  GhostBreath   Cycle #001      Session:     5 min       |
+-----------------------------+---------------------------+
|  CO2    :  1980.0 ppm       |  dC/dt : +312.00 ppm/min |
|  TEG    :   0.000 V         |  Score :  0.8070          |
|  Status : ALERT / HIGH FATIGUE |  Alert :  ON           |
+---------------------------------------------------------+

  [scores] f_co2=0.993  f_rate=1.000  f_time=0.057
  [weights] 0.60*0.993 + 0.20*1.000 + 0.20*0.057 = 0.8070
```

---

## Screenshots to Capture for Report

### Screenshot 1 — Safe state
- CO₂ pot counter-clockwise (420 ppm)
- OLED shows `SAFE`, score < 0.30, LED OFF

### Screenshot 2 — Mild / High Fatigue
- CO₂ pot at ~50% (1460 ppm), early cycles
- OLED shows `MILD FATIGUE` or `HIGH FATIGUE`, LED OFF

### Screenshot 3 — Alert triggered
- CO₂ pot at 75%+ (1980–2500 ppm)
- OLED shows inverted **ALERT** banner, LED ON, buzzer active
- Capture OLED + LED in the same Wokwi circuit view

### Screenshot 4 — Sub-score breakdown (Serial Monitor)
- Show `[scores]` and `[weights]` lines
- Annotate correspondence with Module 4 Python output

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
| Alert threshold | `0.70` (Module 5 firmware) | `ALERT_THRESHOLD 0.70f` |

---

## Power Feasibility (from Modules 1 + 2)

| Parameter | Value | Source |
|-----------|-------|--------|
| TEG output (ΔT=15°C, 50% coupling) | 6.05 mW | Module 1 |
| System load at T=300 s period | 0.50 mW | Module 2 |
| Power headroom | 12× | Module 2 |
| Fatigue scoring cost | ~0.1 ms CPU, 0 mJ extra | Module 4 analysis |

---

## Real Hardware Deployment Notes

To deploy on a physical ESP32 with SCD41 CO₂ sensor:

1. Replace `analogRead(PIN_CO2_ADC)` with SCD41 I²C driver output
2. Replace `analogRead(PIN_TEG_ADC)` with BQ25570 `V_OUT_OK` / MPPT output
3. Uncomment the `esp_deep_sleep_start()` call in `loop()`
4. Comment out `delay(SIM_CYCLE_MS)`
5. The OLED (GPIO21/22) and SCD41 share the I²C bus — different addresses
   (OLED: 0x3C, SCD41: 0x62) so no conflict
6. Install: `arduino-cli lib install "Sensirion I2C SCD4x"`
7. Install: `arduino-cli lib install "Adafruit SSD1306"` and `"Adafruit GFX Library"`

SCD41 wiring: SDA → GPIO 21, SCL → GPIO 22, VDD → 3.3 V, GND → GND
(shares the same I²C bus as the OLED)
