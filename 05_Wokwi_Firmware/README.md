# Module 5 — Embedded Firmware Simulation (Wokwi)

**GhostBreath – Self-Powered Cognitive Fatigue Monitor**
Embedded Systems Course Project · March 2026

---

## Overview

This folder contains the ESP32 firmware for the GhostBreath device, simulated
in [Wokwi](https://wokwi.com) — an online ESP32/Arduino circuit simulator.

The firmware is a **direct embedded port** of the Python fatigue model from
Module 4 (`utils/fatigue_model.py`). Every constant, weight, and formula is
identical; the only differences are language (C vs Python) and input source
(ADC potentiometers replace the CO₂ ODE solver).

**v2 adds:** SSD1306 OLED live display + three Wokwi bug-fixes (ADC range, boot deadlock, buzzer tone). LED removed — buzzer + OLED are sufficient for alert.

---

## Files

| File | Description |
|------|-------------|
| `ghostbreath.ino` | ESP32 Arduino sketch — full fatigue monitor firmware (v2) |
| `diagram.json` | Wokwi circuit diagram — ESP32 + 2 pots + LED + buzzer + OLED |
| `libraries.txt` | Adafruit library declarations for Wokwi.com Library Manager |
| `README.md` | This file |

---

## Circuit Layout

```
                   ┌──────────────────────────────┐
  CO₂ pot (GPIO34)─┤ ADC1_CH6                     │
  TEG pot (GPIO35)─┤ ADC1_CH7                     │
                   │   ESP32                       │──GPIO 4──────────[Buzzer]──GND
                   │   DevKit v1                   │
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
| Buzzer | 4 | Fatigue alert tone — 1 kHz via `tone()` when score ≥ 0.70 |
| SSD1306 OLED 128×64 | 21 (SDA), 22 (SCL) | Live CO₂ / score / status display |

---

## Wokwi Bug-Fixes Applied in v2

| # | Root Cause | Symptom | Fix |
|---|-----------|---------|-----|
| 1 | `analogRead()` defaults to `ADC_0db` (0–1.1 V range); pot signals above ~1.1 V read as 0 | CO₂ locked at 420 ppm; score never crosses 0.70; LED/buzzer never fire | `analogSetAttenuation(ADC_11db)` in `setup()` |
| 2 | `while (!Serial) delay(10)` deadlocks `setup()` on some Wokwi builds | Firmware hangs on boot; no cycles ever execute | Removed the guard |
| 3 | `wokwi-buzzer` requires a frequency signal; `digitalWrite(HIGH)` is silent | LED lights but buzzer makes no sound | `tone(PIN_BUZZER, 1000)` / `noTone()` |
| 4 | Non-ALERT status text used `setTextSize(1)` (8 px) — too small to read in Wokwi's circuit view. LED was removed (buzzer + OLED are sufficient for alert). | OLED states other than ALERT appeared invisible at small font size | Changed non-ALERT status display to `setTextSize(2)` with two-line layout for MILD/HIGH; removed LED and resistor from circuit entirely |

---

## OLED Display

Each cycle the SSD1306 screen refreshes with four lines:

```
┌────────────────────────┐
│ GhostBreath            │  ← fixed title
│────────────────────────│
│ CO2: 1980 ppm          │  ← live ADC reading
│ Score: 0.807           │  ← fatigue risk score [0.0–1.0]
│                        │
│ ██████████████████████ │  ← ALERT state: white banner, large black text
│ █      ALERT         █ │
└────────────────────────┘
```

| Score range | OLED Line 4 | Font size | Background |
|-------------|-------------|-----------|------------|
| < 0.30 | `SAFE` | Small (size 1) | Black |
| 0.30 – 0.60 | `MILD FATIGUE` | Small (size 1) | Black |
| 0.60 – 0.70 | `HIGH FATIGUE` | Small (size 1) | Black |
| ≥ 0.70 | `ALERT` | Large (size 2) | **White** (inverted — black text on white) |

---

## Library Setup

### Option A — Library Manager on wokwi.com (recommended)

1. Open your Wokwi project
2. Click the **"Library Manager"** tab in the editor panel
3. Click the **+** button and search for **`Adafruit SSD1306`**
4. Click **Add** — Adafruit GFX Library is pulled in automatically as a dependency
5. Close Library Manager; `libraries.txt` is now created in the project

### Option B — Paste `libraries.txt` manually

Create a new file named exactly `libraries.txt` (`.txt` extension — wokwi.com
**does not** accept `.toml`) and paste:

```
Adafruit GFX Library
Adafruit SSD1306
```

The file `05_Wokwi_Firmware/libraries.txt` in this repo is ready to copy.

> **VS Code / Wokwi CLI users:** Both `libraries.txt` and `wokwi.toml` work
> with the extension/CLI. On wokwi.com only `.txt` is accepted.

---

## Firmware Behaviour

Each cycle represents **5 real minutes** of study time (simulated as a 5-second
`delay()` in Wokwi):

```
Wake
 │
 ├─ Read ADC 34 × 8 samples → CO₂ ppm  (left pot maps 420–2500 ppm)
 ├─ Read ADC 35 × 8 samples → TEG V    (right pot maps 0–3.3 V)
 ├─ Compute dC/dt = (C_now − C_prev) / 5 min
 │
 ├─ score = 0.60·f_co2(C) + 0.20·f_rate(dC/dt) + 0.20·f_time(t)
 │     f_co2(C)  = sigmoid(0.004 × (C − 1250))
 │     f_rate(r) = clip(r / 15, −1, +1) scaled to [0, 1]
 │     f_time(t) = sigmoid(0.033 × (t − 90))
 │
 ├─ If score ≥ 0.70  →  LED ON  +  tone(buzzer, 1 kHz)  +  OLED ALERT banner
 ├─ Else             →  LED OFF +  noTone(buzzer)         +  OLED status text
 │
 ├─ Serial: formatted cycle table + sub-score breakdown (115200 baud)
 │
 └─ delay(5000 ms)   ← simulates 5-min deep sleep in Wokwi
```

### Score classification

| Score | Label | LED | Buzzer |
|-------|-------|-----|--------|
| 0.00 – 0.30 | SAFE | Silent |
| 0.30 – 0.60 | MILD FATIGUE | Silent |
| 0.60 – 0.70 | HIGH FATIGUE | Silent |
| ≥ 0.70 | ALERT | **1 kHz** |

---

## How to Set Up the Simulation (Full Steps)

### Step 1 — Create the project

1. Go to **[wokwi.com](https://wokwi.com)**
2. Click **"New Project"** → select **"ESP32"**

### Step 2 — Paste the firmware

1. Click the **`sketch.ino`** tab
2. Select all (Ctrl+A) and delete
3. Paste the full contents of `ghostbreath.ino`

### Step 3 — Paste the circuit diagram

1. Click the **`diagram.json`** tab
2. Select all (Ctrl+A) and delete
3. Paste the full contents of `diagram.json`
4. The circuit view should now show: ESP32 + 2 potentiometers + red LED + buzzer + SSD1306 OLED
5. **Check:** the OLED should have coloured wires connecting it to the ESP32 (blue, cyan, red, black). If it shows a `?` badge, re-paste `diagram.json` from the current version of this repo.

### Step 4 — Install libraries

1. Click the **"Library Manager"** tab
2. Click **+** → search **`Adafruit SSD1306`** → **Add**
3. Both Adafruit SSD1306 and Adafruit GFX Library appear in "Installed Libraries"

### Step 5 — Start the simulation

Click the green **▶ Start Simulation** button.

---

## Potentiometer Controls — How to Use the Dials

Wokwi renders each potentiometer as a round dial with a small tick mark.

### Interacting with the dial

| Action | How to do it in Wokwi |
|--------|----------------------|
| Turn clockwise (increase) | Click and **drag right or upward** |
| Turn counter-clockwise (decrease) | Click and **drag left or downward** |
| Fine control | **Scroll mouse wheel** while hovering over the knob |
| Reset to 0% | Right-click the knob → **Reset** |

### Reading the dial position by clock face

```
     12 o'clock = 50%
          │
 9 o'clock ── [knob] ── 3 o'clock
  (0% / min)              (100% / max)
```

- **9 o'clock** (tick pointing left) = **0%** = minimum
- **12 o'clock** (tick pointing straight up) = **50%** = midpoint
- **3 o'clock** (tick pointing right) = **100%** = maximum

### CO₂ potentiometer (left dial, GPIO34)

This is the **primary control**. It maps 0–100% dial rotation to 420–2500 ppm CO₂.

| Dial position | Clock face | CO₂ ppm | f_co₂ score | Study session context |
|---------------|-----------|---------|------------|----------------------|
| 0% | 9 o'clock (fully left) | 420 ppm | 0.035 | Clean outdoor air |
| ~33% | ~11 o'clock | ~1110 ppm | 0.374 | Mild classroom, window open |
| 50% | 12 o'clock (straight up) | ~1460 ppm | 0.698 | Stuffy room, 1 hr study |
| ~65% | ~1 o'clock | ~1750 ppm | 0.872 | Poor ventilation, 2 hrs |
| **75%** | **~2 o'clock** | **~1980 ppm** | **0.938** | **Default — alert fires in 1–2 cycles** |
| 100% | 3 o'clock (fully right) | 2500 ppm | 0.993 | Severe, alert fires immediately |

> **Default:** `diagram.json` sets the CO₂ dial to **75%** so the simulation
> demonstrates an alert without any manual adjustment. If you want to see SAFE
> first, turn it fully left before pressing ▶.

### TEG potentiometer (right dial, GPIO35)

This dial simulates the TEG boost voltage (0–3.3 V). It is displayed on the
OLED and serial output for completeness but **has no effect on the fatigue
score**. Leave it at any position.

---

## Step-by-Step Demo Walkthrough

The following describes exactly what you should see at each stage of the
simulation with the CO₂ pot at its default 75% position.

### Stage 1 — Boot (0–1 second)

**What happens:**
- OLED shows the splash screen:
  ```
  GhostBreath v2
  CO2 Fatigue Monitor

  Initialising...
  ```
- Buzzer: silent

**What to look for:** OLED text visible on the blue display tile in the circuit view.

---

### Stage 2 — First cycle fires (5 seconds after start)

**What happens:**
- OLED refreshes to live readings
- CO₂ reads ~1980 ppm (dial at 75%)
- Rate = (1980 − 420) / 5 = +312 ppm/min → clamped to max → f_rate = 1.0
- f_time(5 min) = 0.057 (session just started)
- **Score = 0.60 × 0.938 + 0.20 × 1.0 + 0.20 × 0.057 = 0.563 + 0.200 + 0.011 = 0.807**

**What you see:**
```
GhostBreath
────────────
CO2: 1980 ppm
Score: 0.807
████████████  ← white filled rectangle
█  ALERT   █  ← large black text on white
████████████
```
- **LED:** bright red — ON
- **Buzzer:** audible 1 kHz tone
- **Serial:** `Cycle #001 | Score: 0.8070 | Alert: ON`

---

### Stage 3 — Turn CO₂ dial counter-clockwise to 50% (12 o'clock)

Wait for the next cycle (~5 seconds).

**What happens:**
- CO₂ reads ~1460 ppm
- Rate = (1460 − 1980) / 5 = −104 ppm/min → clamped → f_rate = 0.0
  (CO₂ is falling, so rate penalty applies)
- f_time(10 min) = 0.064
- **Score = 0.60 × 0.698 + 0.20 × 0.0 + 0.20 × 0.064 = 0.419 + 0.000 + 0.013 = 0.432**

> Score < 0.70 → alert clears

**What you see:**
```
GhostBreath
────────────
CO2: 1460 ppm
Score: 0.432

MILD FATIGUE   ← normal small text, black background
```
- **LED:** OFF
- **Buzzer:** silent

---

### Stage 4 — Turn CO₂ dial fully counter-clockwise (0%, 9 o'clock)

Wait for next cycle.

**What happens:**
- CO₂ = 420 ppm
- **Score ≈ 0.13** (very low CO₂, session still young)

**What you see:**
```
GhostBreath
────────────
CO2: 420 ppm
Score: 0.131

SAFE           ← small text
```
- **LED:** OFF
- **Buzzer:** silent

---

### Stage 5 — Turn CO₂ dial fully clockwise (100%, 3 o'clock)

Wait for next cycle.

**What happens:**
- CO₂ = 2500 ppm
- Rate = (2500 − 420) / 5 = +416 ppm/min → clamped → f_rate = 1.0
- **Score ≈ 0.85**

**What you see:**
```
GhostBreath
────────────
CO2: 2500 ppm
Score: 0.851
████████████
█  ALERT   █   ← ALERT banner returns
████████████
```
- **LED:** ON
- **Buzzer:** 1 kHz

---

## What Correct Output Looks Like — Quick Reference

### OLED states at each dial position

| CO₂ Dial | Approx ppm | OLED status text | OLED style | LED | Buzzer |
|-----------|-----------|-----------------|------------|-----|--------|
| 0% — 9 o'clock | 420 | `SAFE` | Small, white on black | OFF | Silent |
| ~33% — 11 o'clock | ~1110 | `MILD FATIGUE` | Small, white on black | OFF | Silent |
| ~50% — 12 o'clock | ~1460 | `MILD FATIGUE` → `HIGH FATIGUE` | Small, white on black | OFF | Silent |
| ~65% — 1 o'clock | ~1750 | `HIGH FATIGUE` (cycles 1–2) → `ALERT` (later) | Transitions | OFF→ON | Silent→1kHz |
| **75% — 2 o'clock** | **~1980** | **`ALERT`** | **Large, black on white** | **ON** | **1 kHz** |
| 100% — 3 o'clock | 2500 | `ALERT` | Large, black on white | ON | 1 kHz |

### Serial Monitor output (optional, 115200 baud)

When the OLED shows `ALERT`:
```
+---------------------------------------------------------+
|  GhostBreath   Cycle #001      Session:     5 min       |
+-----------------------------+---------------------------+
|  CO2    :  1980.0 ppm       |  dC/dt : +312.00 ppm/min |
|  TEG    :   0.000 V         |  Score :  0.8070          |
|  Status : ALERT / HIGH FATIGUE |  Alert :  ON           |
+---------------------------------------------------------+

  [scores] f_co2=0.938  f_rate=1.000  f_time=0.057
  [weights] 0.60*0.938 + 0.20*1.000 + 0.20*0.057 = 0.8070
```

When the OLED shows `SAFE` (dial at 0%):
```
|  CO2    :   420.0 ppm       |  dC/dt :    +0.00 ppm/min |
|  Score :  0.1312            |  Alert :  OFF              |
  [scores] f_co2=0.035  f_rate=0.500  f_time=0.057
```

---

## Troubleshooting

| Symptom | Most Likely Cause | Fix |
|---------|------------------|-----|
| OLED completely black, no text | Adafruit SSD1306 library not installed | Open Library Manager → Add "Adafruit SSD1306" |
| OLED shows a `?` badge on the component | Wrong pin names in old `diagram.json` (`esp:SDA` / `esp:SCL` don't exist) | Re-paste the current `diagram.json` from this repo |
| OLED has wires but stays black | I2C address mismatch (rare) | The firmware uses `0x3C` — standard for 128×64 SSD1306 modules |
| LED never lights even with dial at max | Old `diagram.json`/`ghostbreath.ino` — either `esp:GND.3` (bad GND) or still using GPIO2 (internal onboard LED causes voltage drop) | Re-paste both `ghostbreath.ino` and `diagram.json` from this repo; LED self-test at boot confirms the fix |
| Buzzer icon shows but produces no sound | Old `.ino` using `digitalWrite(HIGH)` instead of `tone()` | Re-paste current `ghostbreath.ino` (v2) |
| Score shown on OLED never crosses 0.70 | ADC attenuation bug in old firmware | Re-paste `ghostbreath.ino` (v2); also try turning dial fully clockwise |
| Simulation appears frozen / no output | Old `.ino` with `while (!Serial) delay(10)` deadlock | Re-paste `ghostbreath.ino` (v2) |
| OLED shows readings, dial at 75%, but score is ~0.13 | You re-ran with `s_prev_co2` = 1980; rate = 0 so first-cycle spike is missing | Normal — score will still be ~0.63 (above threshold after study time builds) |
| Score ≈ 0.43 after turning dial down then back up | CO₂ fell first (negative rate) → lower f_rate | Normal physics; wait 1 more cycle or set dial to 100% for instant ALERT |

---

## Screenshots to Capture for Report

### Screenshot 1 — SAFE state
- CO₂ dial at **0%** (9 o'clock, fully left)
- OLED shows `SAFE`, score < 0.30
- LED OFF

### Screenshot 2 — MILD FATIGUE
- CO₂ dial at **~33%** (11 o'clock)
- OLED shows `MILD FATIGUE`, score 0.30–0.60
- LED OFF

### Screenshot 3 — HIGH FATIGUE (no alert)
- CO₂ dial at **50%** (12 o'clock)
- OLED shows `HIGH FATIGUE`, score 0.60–0.70
- LED OFF

### Screenshot 4 — ALERT triggered
- CO₂ dial at **75–100%** (2–3 o'clock)
- OLED shows large **ALERT** banner (inverted: white background, black text)
- **LED ON** (bright red visible in circuit view)
- Buzzer active (1 kHz)
- Capture both OLED and LED in the same Wokwi circuit view

### Screenshot 5 — Sub-score breakdown (Serial Monitor)
- Open Serial Monitor at 115200 baud
- Show the `[scores]` and `[weights]` debug lines
- Annotate the correspondence with Module 4 Python model output

---

## Firmware–Model Consistency Verification

All constants in `ghostbreath.ino` are identical to `utils/fatigue_model.py`:

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
| Alert threshold | `0.70` | `ALERT_THRESHOLD 0.70f` |

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
5. The OLED (GPIO21/22) and SCD41 share the I²C bus — different I²C addresses
   (OLED: 0x3C, SCD41: 0x62) so no conflict
6. Install: `arduino-cli lib install "Sensirion I2C SCD4x"`
7. Install: `arduino-cli lib install "Adafruit SSD1306"` and `"Adafruit GFX Library"`

SCD41 wiring: SDA → GPIO 21, SCL → GPIO 22, VDD → 3.3 V, GND → GND
(shares the same I²C bus as the OLED)
