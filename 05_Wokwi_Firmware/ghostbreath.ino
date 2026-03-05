/**
 * GhostBreath – Cognitive Fatigue Monitor  |  Module 5
 * =====================================================
 * Embedded firmware for ESP32 (DevKit v1), simulated in Wokwi.
 *
 * Hardware (simulated):
 *   GPIO 34  – Potentiometer  →  CO₂ concentration (420–2500 ppm)
 *   GPIO 35  – Potentiometer  →  TEG boost voltage  (0–3.3 V)
 *   GPIO  2  – LED            →  Fatigue alert indicator (active HIGH)
 *   GPIO  4  – Buzzer         →  Fatigue alert buzzer   (active HIGH)
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
 *   score < 0.30   →  SAFE
 *   0.30 ≤ score < 0.60  →  MILD FATIGUE
 *   0.60 ≤ score < 0.70  →  HIGH FATIGUE  (no alert yet)
 *   score ≥ 0.70   →  ALERT  (LED + buzzer)
 *
 * Reference: Allen et al. (2016) Harvard CogFx study.
 */

#include <math.h>

// ─── Pin assignments ───────────────────────────────────────────────────────────
#define PIN_CO2_ADC   34   // ADC1_CH6 — CO₂ simulation potentiometer
#define PIN_TEG_ADC   35   // ADC1_CH7 — TEG voltage simulation potentiometer
#define PIN_LED        2   // Alert LED (active HIGH)
#define PIN_BUZZER     4   // Active buzzer (active HIGH)

// ─── Duty-cycle timing ────────────────────────────────────────────────────────
// Real hardware: SCD41 reads every SLEEP_DURATION_MIN minutes via deep sleep.
// Wokwi sim: SIM_CYCLE_MS milliseconds per cycle for real-time observation.
#define SLEEP_DURATION_MIN   5       // [min]  — real measurement interval
#define SIM_CYCLE_MS      5000       // [ms]   — simulated as 5-second cycles

// ─── ADC input mapping ────────────────────────────────────────────────────────
#define ADC_BITS         12          // ESP32 ADC resolution
#define ADC_MAX        4095.0f       // 2^12 - 1

// CO₂ potentiometer → ppm range matching Module 3 simulation
#define CO2_PPM_MIN    420.0f        // ambient outdoor CO₂ [ppm]
#define CO2_PPM_MAX   2500.0f        // upper sim range [ppm]

// TEG potentiometer → voltage range matching Module 1 boost output
#define TEG_V_MIN       0.0f         // [V]
#define TEG_V_MAX       3.3f         // [V] — ESP32 ADC reference

// ─── Fatigue model constants (must match utils/fatigue_model.py exactly) ──────
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

// Alert threshold (ESP32 fires LED + buzzer above this score)
#define ALERT_THRESHOLD   0.70f

// Score band boundaries (for serial classification label)
#define SCORE_MILD  0.30f
#define SCORE_HIGH  0.60f

// ─── Session state ────────────────────────────────────────────────────────────
static uint32_t s_cycle        = 0;
static float    s_study_min    = 0.0f;   // accumulated study time [min]
static float    s_prev_co2     = CO2_PPM_MIN;  // previous CO₂ reading [ppm]

// ─── Sub-score helpers ────────────────────────────────────────────────────────

/**
 * Fast sigmoid using single-precision expf().
 * Equivalent to Python: 1.0 / (1.0 + np.exp(-x))
 */
float sigmoid(float x) {
  return 1.0f / (1.0f + expf(-x));
}

/**
 * CO₂ sub-score — logistic function centred at 1250 ppm.
 * Python equiv: _f_co2(C) in utils/fatigue_model.py
 */
float f_co2(float C_ppm) {
  return sigmoid(CO2_SCALE * (C_ppm - CO2_CENTRE));
}

/**
 * Rate-of-change sub-score — linear mapping of dC/dt onto [0, 1].
 * Python equiv: _f_rate(dCdt) in utils/fatigue_model.py
 *   dCdt ≤ −RATE_MAX → 0.0 (CO₂ falling rapidly)
 *   dCdt = 0          → 0.5 (stable)
 *   dCdt ≥ +RATE_MAX → 1.0 (CO₂ rising rapidly)
 */
float f_rate(float dCdt_ppm_min) {
  float norm = dCdt_ppm_min / RATE_MAX;
  if (norm >  1.0f) norm =  1.0f;
  if (norm < -1.0f) norm = -1.0f;
  return (norm + 1.0f) * 0.5f;
}

/**
 * Study-time sub-score — logistic function centred at 90 min.
 * Python equiv: _f_time(study_time_min) in utils/fatigue_model.py
 */
float f_time(float study_min) {
  return sigmoid(TIME_SCALE * (study_min - TIME_CENTRE));
}

// ─── Fatigue score ────────────────────────────────────────────────────────────

/**
 * Weighted sum fatigue risk score ∈ [0, 1].
 * Exact port of fatigue_score() in utils/fatigue_model.py:
 *   score = W_CO2·f_co2(C) + W_RATE·f_rate(dCdt) + W_TIME·f_time(t)
 *
 * @param C_ppm        CO₂ concentration [ppm]
 * @param dCdt_ppm_min Rate of CO₂ change [ppm/min]
 * @param study_min    Elapsed study time [min]
 * @return Fatigue risk score [0.0, 1.0]
 */
float fatigue_score(float C_ppm, float dCdt_ppm_min, float study_min) {
  float score = W_CO2  * f_co2(C_ppm)
              + W_RATE * f_rate(dCdt_ppm_min)
              + W_TIME * f_time(study_min);
  if (score < 0.0f) score = 0.0f;
  if (score > 1.0f) score = 1.0f;
  return score;
}

// ─── Classification label ─────────────────────────────────────────────────────
const char* classify(float score) {
  if (score >= ALERT_THRESHOLD) return "ALERT / HIGH FATIGUE";
  if (score >= SCORE_HIGH)      return "HIGH FATIGUE";
  if (score >= SCORE_MILD)      return "MILD FATIGUE";
  return "SAFE";
}

// ─── ADC → physical unit helpers ─────────────────────────────────────────────

float read_co2_ppm() {
  int raw = analogRead(PIN_CO2_ADC);
  return CO2_PPM_MIN + (raw / ADC_MAX) * (CO2_PPM_MAX - CO2_PPM_MIN);
}

float read_teg_voltage() {
  int raw = analogRead(PIN_TEG_ADC);
  return TEG_V_MIN + (raw / ADC_MAX) * (TEG_V_MAX - TEG_V_MIN);
}

// ─── Alert output ─────────────────────────────────────────────────────────────
void set_alert(bool active) {
  digitalWrite(PIN_LED,    active ? HIGH : LOW);
  digitalWrite(PIN_BUZZER, active ? HIGH : LOW);
}

// ─── One measurement + scoring cycle ─────────────────────────────────────────
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

  // 4. Set alert outputs
  set_alert(alert);

  // 5. Serial debug output
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

  // ── Sub-score breakdown (useful for verification against Module 4) ──────────
  Serial.printf("  [scores] f_co2=%.3f  f_rate=%.3f  f_time=%.3f\n",
                f_co2(co2_ppm), f_rate(dCdt), f_time(s_study_min));
  Serial.printf("  [weights] %.2f*%.3f + %.2f*%.3f + %.2f*%.3f = %.4f\n",
                W_CO2,  f_co2(co2_ppm),
                W_RATE, f_rate(dCdt),
                W_TIME, f_time(s_study_min),
                score);
  Serial.println();
}

// ─── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  pinMode(PIN_LED,    OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  analogReadResolution(ADC_BITS);
  set_alert(false);

  Serial.println();
  Serial.println(F("+=======================================================+"));
  Serial.println(F("|        GhostBreath -- Cognitive Fatigue Monitor       |"));
  Serial.println(F("|        Battery-free  |  TEG-powered  |  ESP32         |"));
  Serial.println(F("+=======================================================+"));
  Serial.printf( "|  Real cycle period  : %d min (deep sleep)              |\n",
                 SLEEP_DURATION_MIN);
  Serial.printf( "|  Sim cycle period   : %d s  (Wokwi delay)              |\n",
                 SIM_CYCLE_MS / 1000);
  Serial.println(F("|  Alert threshold    : score >= 0.70                   |"));
  Serial.println(F("|  CO2 input range    : 420-2500 ppm (left pot)         |"));
  Serial.println(F("|  TEG input range    : 0-3.3 V      (right pot)        |"));
  Serial.println(F("+-------------------------------------------------------+"));
  Serial.println(F("|  Model: score = 0.60*f_co2 + 0.20*f_rate + 0.20*f_t |"));
  Serial.println(F("|    f_co2  : sigmoid(0.004*(C - 1250))                 |"));
  Serial.println(F("|    f_rate : clip(dCdt/15, -1,+1) -> [0,1]            |"));
  Serial.println(F("|    f_time : sigmoid(0.033*(t - 90))                   |"));
  Serial.println(F("+=======================================================+"));
  Serial.println();
  Serial.println(F("Wokwi controls:"));
  Serial.println(F("  Left  pot (GPIO34) -- Turn clockwise to raise CO2 ppm"));
  Serial.println(F("  Right pot (GPIO35) -- Turn clockwise to raise TEG V"));
  Serial.println(F("  Watch LED + buzzer -- activate when score >= 0.70"));
  Serial.println(F("  Each printed cycle represents 5 real study minutes"));
  Serial.println();
  Serial.println(F("--- Starting measurement loop ---"));
  Serial.println();
}

// ─── Main loop ────────────────────────────────────────────────────────────────
void loop() {
  run_cycle();

  // ── Real hardware deep sleep (commented out for Wokwi simulation) ───────────
  // On actual ESP32, replace delay() with:
  //   uint64_t sleep_us = (uint64_t)SLEEP_DURATION_MIN * 60ULL * 1000000ULL;
  //   esp_sleep_enable_timer_wakeup(sleep_us);
  //   esp_deep_sleep_start();   // resumes at setup() after wake

  delay(SIM_CYCLE_MS);
}
