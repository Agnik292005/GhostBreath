/**
 * GhostBreath – Cognitive Fatigue Monitor  |  Module 5  (v2 — OLED edition)
 * =========================================================================
 * Embedded firmware for ESP32 (DevKit v1), simulated in Wokwi.
 *
 * Hardware (simulated):
 *   GPIO 34  – Potentiometer  →  CO₂ concentration (420–2500 ppm)
 *   GPIO 35  – Potentiometer  →  TEG boost voltage  (0–3.3 V)
 *   GPIO  4  – Buzzer         →  Fatigue alert tone (1 kHz via tone())
 *   GPIO 21  – OLED SDA       →  SSD1306 I2C data
 *   GPIO 22  – OLED SCL       →  SSD1306 I2C clock
 *
 * Duty-cycle behaviour (mirrors Module 2 parameters):
 *   Real device  : deep-sleep 5 min between SCD41 readings
 *   Wokwi sim    : delay(SIM_CYCLE_MS) so cycles are observable in real time
 *
 * Fatigue model (exact port of utils/fatigue_model.py):
 *   score = 0.60·f_co2(C) + 0.20·f_rate(dC/dt) + 0.20·f_time(t)
 *   Alert fires when score ≥ ALERT_THRESHOLD (0.70)
 *
 * Score thresholds (consistent with Module 4):
 *   score <  0.30              →  SAFE
 *   0.30 ≤ score < 0.60        →  MILD FATIGUE
 *   0.60 ≤ score < 0.70        →  HIGH FATIGUE  (no alert yet)
 *   score ≥ 0.70               →  ALERT  (buzzer + OLED inverted)
 *
 * Bug-fixes vs v1
 * ---------------
 *   1. analogSetAttenuation(ADC_11db) — ensures full 0-3.3 V ADC range;
 *      without this, voltages above ~1.1 V read as 0 in some Wokwi builds,
 *      locking CO₂ at 420 ppm and preventing any alert.
 *   2. Removed "while (!Serial)" guard — could deadlock setup() in Wokwi.
 *   3. Buzzer now uses tone()/noTone() — wokwi-buzzer requires a frequency
 *      signal; digitalWrite(HIGH) produces no sound in the simulator.
 *
 * Reference: Allen et al. (2016) Harvard CogFx study.
 */

#include <math.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ─── OLED display object ───────────────────────────────────────────────────
#define OLED_W  128
#define OLED_H   64
#define OLED_RST  -1   // shared reset with ESP32 EN pin
Adafruit_SSD1306 display(OLED_W, OLED_H, &Wire, OLED_RST);

// ─── Pin assignments ───────────────────────────────────────────────────────
#define PIN_CO2_ADC   34   // ADC1_CH6 — CO₂ simulation potentiometer
#define PIN_TEG_ADC   35   // ADC1_CH7 — TEG voltage simulation potentiometer
#define PIN_BUZZER     4   // Buzzer driven via tone() for Wokwi compatibility
#define PIN_SDA       21   // OLED I2C data
#define PIN_SCL       22   // OLED I2C clock

// ─── Duty-cycle timing ────────────────────────────────────────────────────
#define SLEEP_DURATION_MIN   5       // [min]  real measurement interval
#define SIM_CYCLE_MS      5000       // [ms]   simulated as 5-second cycles

// ─── ADC input mapping ────────────────────────────────────────────────────
#define ADC_BITS         12          // ESP32 ADC resolution
#define ADC_MAX        4095.0f       // 2^12 - 1

// CO₂ potentiometer → ppm range matching Module 3 simulation
#define CO2_PPM_MIN    420.0f        // ambient outdoor CO₂ [ppm]
#define CO2_PPM_MAX   2500.0f        // upper sim range [ppm]

// TEG potentiometer → voltage range matching Module 1 boost output
#define TEG_V_MIN       0.0f         // [V]
#define TEG_V_MAX       3.3f         // [V]

// ─── Fatigue model constants (must match utils/fatigue_model.py exactly) ─
// Weights (sum = 1.0)
#define W_CO2    0.60f
#define W_RATE   0.20f
#define W_TIME   0.20f

// f_co2 sigmoid: centred at 1250 ppm, scale 0.004 ppm⁻¹
//   At 420 ppm → ≈ 0.04   At 1250 ppm → 0.50   At 2500 ppm → ≈ 0.97
#define CO2_CENTRE  1250.0f
#define CO2_SCALE      0.004f

// f_time sigmoid: centred at 90 min, scale 0.033 min⁻¹
//   At   0 min → ≈ 0.05   At  90 min → 0.50   At 180 min → ≈ 0.95
#define TIME_CENTRE   90.0f
#define TIME_SCALE     0.033f

// f_rate linear clamp: maps dC/dt ∈ [−15, +15] ppm/min → [0, 1]
#define RATE_MAX   15.0f

// Alert threshold (ESP32 fires LED + buzzer + OLED invert above this score)
#define ALERT_THRESHOLD   0.70f

// Score band boundaries
#define SCORE_MILD  0.30f
#define SCORE_HIGH  0.60f

// Buzzer alert frequency [Hz]
#define ALERT_TONE_HZ  1000

// ─── Session state ────────────────────────────────────────────────────────
// RTC_DATA_ATTR preserves variables across deep-sleep cycles.
// In Wokwi (delay-based), plain static works identically.
RTC_DATA_ATTR static uint32_t s_cycle     = 0;
RTC_DATA_ATTR static float    s_study_min = 0.0f;
RTC_DATA_ATTR static float    s_prev_co2  = CO2_PPM_MIN;

// ─── Sigmoid helper ───────────────────────────────────────────────────────
/**
 * Fast sigmoid.  Equivalent to Python: 1.0 / (1.0 + np.exp(-x))
 */
float sigmoid(float x) {
  return 1.0f / (1.0f + expf(-x));
}

// ─── Sub-score helpers (identical to utils/fatigue_model.py) ─────────────
float f_co2(float C_ppm) {
  return sigmoid(CO2_SCALE * (C_ppm - CO2_CENTRE));
}

float f_rate(float dCdt_ppm_min) {
  float norm = dCdt_ppm_min / RATE_MAX;
  if (norm >  1.0f) norm =  1.0f;
  if (norm < -1.0f) norm = -1.0f;
  return (norm + 1.0f) * 0.5f;
}

float f_time(float study_min) {
  return sigmoid(TIME_SCALE * (study_min - TIME_CENTRE));
}

// ─── Fatigue score (unchanged from v1) ───────────────────────────────────
float fatigue_score(float C_ppm, float dCdt_ppm_min, float study_min) {
  float score = W_CO2  * f_co2(C_ppm)
              + W_RATE * f_rate(dCdt_ppm_min)
              + W_TIME * f_time(study_min);
  if (score < 0.0f) score = 0.0f;
  if (score > 1.0f) score = 1.0f;
  return score;
}

// ─── Classification helpers ───────────────────────────────────────────────
/** Serial output label (unchanged). */
const char* classify(float score) {
  if (score >= ALERT_THRESHOLD) return "ALERT / HIGH FATIGUE";
  if (score >= SCORE_HIGH)      return "HIGH FATIGUE";
  if (score >= SCORE_MILD)      return "MILD FATIGUE";
  return "SAFE";
}

/** Short status string for the OLED (4-level per task spec). */
const char* oled_status(float score) {
  if (score >= ALERT_THRESHOLD) return "ALERT";
  if (score >= SCORE_HIGH)      return "HIGH FATIGUE";
  if (score >= SCORE_MILD)      return "MILD FATIGUE";
  return "SAFE";
}

// ─── ADC → physical unit helpers (8-sample average for Wokwi stability) ──
float read_co2_ppm() {
  long sum = 0;
  for (int i = 0; i < 8; i++) sum += analogRead(PIN_CO2_ADC);
  float raw = (float)(sum / 8);
  return CO2_PPM_MIN + (raw / ADC_MAX) * (CO2_PPM_MAX - CO2_PPM_MIN);
}

float read_teg_voltage() {
  long sum = 0;
  for (int i = 0; i < 8; i++) sum += analogRead(PIN_TEG_ADC);
  float raw = (float)(sum / 8);
  return TEG_V_MIN + (raw / ADC_MAX) * (TEG_V_MAX - TEG_V_MIN);
}

// ─── Alert output (Bug-fix 3: use tone() so Wokwi buzzer actually sounds) ─
void set_alert(bool active) {
  if (active) {
    tone(PIN_BUZZER, ALERT_TONE_HZ);
  } else {
    noTone(PIN_BUZZER);
  }
}

// ─── OLED display update ──────────────────────────────────────────────────
/**
 * Refresh the SSD1306 screen every cycle.
 *
 * Layout (128×64 px, font size 1 = 6×8 px):
 *   y= 0   "GhostBreath"          — fixed title
 *   y=12   "CO2: XXXX ppm"        — live reading
 *   y=24   "Score: 0.XXX"         — fatigue score
 *   y=40   Status text            — size-2 on ALERT, inverted colours
 */
void update_oled(float co2_ppm, float score, bool alert) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  // Line 1 — title
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println(F("GhostBreath"));

  // Separator line
  display.drawFastHLine(0, 9, OLED_W, SSD1306_WHITE);

  // Line 2 — CO₂
  display.setCursor(0, 12);
  display.print(F("CO2: "));
  display.print((int)co2_ppm);
  display.println(F(" ppm"));

  // Line 3 — fatigue score
  display.setCursor(0, 24);
  display.print(F("Score: "));
  display.println(score, 3);

  // Line 4 — status (size-2 for all states so it's readable in Wokwi's small view)
  if (alert) {
    // Fill banner white, print black text so it stands out
    display.fillRect(0, 38, OLED_W, OLED_H - 38, SSD1306_WHITE);
    display.setTextColor(SSD1306_BLACK);
    display.setTextSize(2);
    display.setCursor(4, 42);
    display.print(F("ALERT"));
  } else {
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(2);
    if (score >= SCORE_HIGH) {
      display.setCursor(0, 36);
      display.print(F("HIGH"));
      display.setTextSize(1);
      display.setCursor(0, 54);
      display.print(F("FATIGUE"));
    } else if (score >= SCORE_MILD) {
      display.setCursor(0, 36);
      display.print(F("MILD"));
      display.setTextSize(1);
      display.setCursor(0, 54);
      display.print(F("FATIGUE"));
    } else {
      display.setCursor(4, 44);
      display.print(F("SAFE"));
    }
  }

  display.display();
}

// ─── One measurement + scoring cycle ─────────────────────────────────────
void run_cycle() {
  s_cycle++;
  s_study_min += (float)SLEEP_DURATION_MIN;

  // 1. Read sensors
  float co2_ppm = read_co2_ppm();
  float teg_v   = read_teg_voltage();

  // 2. Compute rate of change [ppm/min] since last cycle
  float dCdt = (co2_ppm - s_prev_co2) / (float)SLEEP_DURATION_MIN;
  s_prev_co2 = co2_ppm;

  // 3. Score and classify
  float score       = fatigue_score(co2_ppm, dCdt, s_study_min);
  const char* label = classify(score);
  bool  alert       = (score >= ALERT_THRESHOLD);

  // 4. Set alert outputs (LED + buzzer)
  set_alert(alert);

  // 5. OLED live display
  update_oled(co2_ppm, score, alert);

  // 6. Serial debug output (unchanged format from v1)
  Serial.println(F("+---------------------------------------------------------+"));
  Serial.printf( "|  GhostBreath   Cycle #%03u      Session: %5.0f min        |\n",
                 s_cycle, s_study_min);
  Serial.println(F("+-----------------------------+---------------------------+"));
  Serial.printf( "|  CO2    : %7.1f ppm       |  dC/dt : %+8.2f ppm/min |\n",
                 co2_ppm, dCdt);
  Serial.printf( "|  TEG    : %7.3f V          |  Score :  %.4f            |\n",
                 teg_v, score);
  Serial.printf( "|  Status : %-20s |  Alert :  %-3s                |\n",
                 label, alert ? "ON " : "OFF");
  Serial.println(F("+---------------------------------------------------------+"));
  Serial.println();

  Serial.printf("  [scores] f_co2=%.3f  f_rate=%.3f  f_time=%.3f\n",
                f_co2(co2_ppm), f_rate(dCdt), f_time(s_study_min));
  Serial.printf("  [weights] %.2f*%.3f + %.2f*%.3f + %.2f*%.3f = %.4f\n",
                W_CO2,  f_co2(co2_ppm),
                W_RATE, f_rate(dCdt),
                W_TIME, f_time(s_study_min),
                score);
  Serial.println();
}

// ─── Setup ────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  // NOTE: "while (!Serial)" removed — can deadlock Wokwi (Bug-fix 2)

  // Bug-fix 1: set full 0-3.3 V ADC range before any analogRead().
  // Without this, Wokwi maps voltages above ~1.1 V to 0, locking
  // CO₂ at 420 ppm and making the fatigue score unable to reach 0.70.
  analogSetAttenuation(ADC_11db);
  analogReadResolution(ADC_BITS);

  // I2C + OLED initialisation
  Wire.begin(PIN_SDA, PIN_SCL);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("[OLED] SSD1306 init failed — check wiring"));
    // Continue without OLED; Serial Monitor still works
  } else {
    // Splash screen
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println(F("GhostBreath v2"));
    display.println(F("CO2 Fatigue Monitor"));
    display.println();
    display.println(F("Initialising..."));
    display.display();
    delay(1000);
    display.clearDisplay();
    display.display();
  }

  pinMode(PIN_BUZZER, OUTPUT);
  set_alert(false);

  Serial.println();
  Serial.println(F("+=======================================================+"));
  Serial.println(F("|       GhostBreath v2 -- Cognitive Fatigue Monitor     |"));
  Serial.println(F("|   Battery-free  |  TEG-powered  |  ESP32 + OLED       |"));
  Serial.println(F("+=======================================================+"));
  Serial.printf( "|  Real cycle period  : %d min (deep sleep)              |\n",
                 SLEEP_DURATION_MIN);
  Serial.printf( "|  Sim cycle period   : %d s  (Wokwi delay)              |\n",
                 SIM_CYCLE_MS / 1000);
  Serial.println(F("|  Alert threshold    : score >= 0.70                   |"));
  Serial.println(F("|  CO2 input range    : 420-2500 ppm (left pot, GPIO34) |"));
  Serial.println(F("|  TEG input range    : 0-3.3 V      (right pot, GPIO35)|"));
  Serial.println(F("|  OLED display       : SSD1306 128x64 (GPIO21/22 I2C) |"));
  Serial.println(F("+-------------------------------------------------------+"));
  Serial.println(F("|  Model: score = 0.60*f_co2 + 0.20*f_rate + 0.20*f_t |"));
  Serial.println(F("|    f_co2  : sigmoid(0.004*(C - 1250))                 |"));
  Serial.println(F("|    f_rate : clip(dCdt/15, -1,+1) -> [0,1]            |"));
  Serial.println(F("|    f_time : sigmoid(0.033*(t - 90))                   |"));
  Serial.println(F("+=======================================================+"));
  Serial.println();
  Serial.println(F("Bug-fixes applied (v2):"));
  Serial.println(F("  [1] analogSetAttenuation(ADC_11db) -- full 0-3.3V ADC range"));
  Serial.println(F("  [2] Removed while(!Serial) guard  -- no Wokwi deadlock"));
  Serial.println(F("  [3] tone()/noTone() buzzer         -- audible in Wokwi"));
  Serial.println();
  Serial.println(F("Wokwi controls:"));
  Serial.println(F("  Left  pot (GPIO34) -- Clockwise = higher CO2 ppm"));
  Serial.println(F("  Right pot (GPIO35) -- Clockwise = higher TEG voltage"));
  Serial.println(F("  OLED shows CO2 / score / status without Serial Monitor"));
  Serial.println(F("  Buzzer activates when score >= 0.70"));
  Serial.println(F("  Each cycle = 5 seconds sim time = 5 real study minutes"));
  Serial.println();
  Serial.println(F("--- Starting measurement loop ---"));
  Serial.println();
}

// ─── Main loop ────────────────────────────────────────────────────────────
void loop() {
  run_cycle();

  // ── Real hardware deep sleep (commented out for Wokwi simulation) ───────
  // On actual ESP32, replace delay() with:
  //   uint64_t sleep_us = (uint64_t)SLEEP_DURATION_MIN * 60ULL * 1000000ULL;
  //   esp_sleep_enable_timer_wakeup(sleep_us);
  //   esp_deep_sleep_start();   // resumes at setup() after wake

  delay(SIM_CYCLE_MS);
}
