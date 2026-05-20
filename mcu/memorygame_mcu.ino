/*
 * GNMC Memory TalkTalk - MCU Sketch (STM32U585 on Arduino UNO Q)
 *
 * Serial line protocol @ 115200, see mpu/rpc_bridge.py for details.
 *
 * Color codes: R=RED, B=BLUE, Y=YELLOW, G=GREEN
 */

static const char FW_VERSION[] = "1.0.0";

static const uint8_t BTN_PINS[4] = {2, 3, 4, 5};      // R B Y G
static const uint8_t LED_PINS[4] = {6, 9, 10, 11};
static const char COLOR_CHARS[4] = {'R', 'B', 'Y', 'G'};

static const uint16_t DEBOUNCE_MS = 20;
static const uint8_t  LED_BRIGHTNESS = 220;

enum InputMode { IM_DISARMED, IM_ARMED };
static InputMode inputMode = IM_DISARMED;
static bool      armedColors[4] = {false, false, false, false};
static uint32_t  armDeadlineMs = 0;

struct ButtonState {
  bool     stable;       // true = pressed (active low)
  bool     lastReading;
  uint32_t lastChangeMs;
};
static ButtonState btn[4];

struct LedPulse { uint32_t offAtMs; };
static LedPulse pulse[4] = {{0},{0},{0},{0}};

// Sequence playback ----------------------------------------------------------
static bool     seqActive = false;
static char     seqColors[40];
static uint8_t  seqLen = 0;
static uint8_t  seqIdx = 0;
static uint16_t seqOnMs = 500;
static uint16_t seqOffMs = 200;
static uint32_t seqPhaseStartMs = 0;
static bool     seqPhaseOn = false;

// Attract LED rotation -------------------------------------------------------
static bool     attractOn = false;
static uint32_t attractStepMs = 0;
static uint8_t  attractIdx = 0;

// Input buffer ---------------------------------------------------------------
static char rxBuf[64];
static uint8_t rxLen = 0;

static int8_t colorIndex(char c) {
  for (uint8_t i = 0; i < 4; i++) if (COLOR_CHARS[i] == c) return i;
  return -1;
}

static void setLed(uint8_t i, bool on) {
  analogWrite(LED_PINS[i], on ? LED_BRIGHTNESS : 0);
}

static void pulseLed(uint8_t i, uint16_t ms) {
  setLed(i, true);
  pulse[i].offAtMs = millis() + ms;
}

static void setAllLeds(bool on) {
  for (uint8_t i = 0; i < 4; i++) setLed(i, on);
}

static void println(const char *s) { Serial.println(s); }
static void printErr(const char *s) { Serial.print("ERR "); Serial.println(s); }

static void handleLight(char *args) {
  // "<C> <ms>"
  if (!args) { printErr("args"); return; }
  char c = args[0];
  int8_t i = colorIndex(c);
  if (i < 0) { printErr("color"); return; }
  long ms = atol(args + 2);
  if (ms <= 0 || ms > 5000) { printErr("ms"); return; }
  pulseLed((uint8_t)i, (uint16_t)ms);
  println("OK");
}

static void handlePlay(char *args) {
  // "<colors> <on_ms> <off_ms>"
  if (!args) { printErr("args"); return; }
  char *sp1 = strchr(args, ' ');
  if (!sp1) { printErr("syntax"); return; }
  *sp1 = '\0';
  char *sp2 = strchr(sp1 + 1, ' ');
  if (!sp2) { printErr("syntax"); return; }
  *sp2 = '\0';

  uint8_t len = strlen(args);
  if (len == 0 || len > sizeof(seqColors)) { printErr("len"); return; }
  for (uint8_t i = 0; i < len; i++) {
    if (colorIndex(args[i]) < 0) { printErr("color"); return; }
    seqColors[i] = args[i];
  }
  long onMs = atol(sp1 + 1);
  long offMs = atol(sp2 + 1);
  if (onMs <= 0 || offMs < 0 || onMs > 5000 || offMs > 5000) { printErr("ms"); return; }

  seqLen = len;
  seqIdx = 0;
  seqOnMs = (uint16_t)onMs;
  seqOffMs = (uint16_t)offMs;
  seqPhaseOn = true;
  seqPhaseStartMs = millis();
  seqActive = true;

  int8_t ci = colorIndex(seqColors[0]);
  if (ci >= 0) setLed((uint8_t)ci, true);

  println("OK");
}

static void handleAll(char *args) {
  if (!args) { printErr("args"); return; }
  if (!strcmp(args, "ON")) { setAllLeds(true); println("OK"); }
  else if (!strcmp(args, "OFF")) { setAllLeds(false); println("OK"); }
  else printErr("arg");
}

static void handleAttract(char *args) {
  if (!args) { printErr("args"); return; }
  if (!strcmp(args, "ON")) {
    attractOn = true; attractIdx = 0; attractStepMs = millis();
    setAllLeds(false);
    println("OK");
  } else if (!strcmp(args, "OFF")) {
    attractOn = false;
    setAllLeds(false);
    println("OK");
  } else printErr("arg");
}

static void handleArm(char *args) {
  if (!args) { printErr("args"); return; }
  char *sp = strchr(args, ' ');
  if (!sp) { printErr("syntax"); return; }
  *sp = '\0';
  for (uint8_t i = 0; i < 4; i++) armedColors[i] = false;
  for (uint8_t i = 0; args[i]; i++) {
    int8_t ci = colorIndex(args[i]);
    if (ci < 0) { printErr("color"); return; }
    armedColors[ci] = true;
  }
  long ms = atol(sp + 1);
  if (ms <= 0 || ms > 60000) { printErr("ms"); return; }
  armDeadlineMs = millis() + (uint32_t)ms;
  inputMode = IM_ARMED;
  println("OK");
}

static void handleDisarm() {
  inputMode = IM_DISARMED;
  println("OK");
}

static void handleSelftest() {
  for (uint8_t i = 0; i < 4; i++) {
    setLed(i, true);
    delay(150);
    setLed(i, false);
  }
  Serial.println("SELFTEST OK");
}

static void handleVersion() {
  Serial.print("VER ");
  Serial.println(FW_VERSION);
}

static void dispatch(char *line) {
  while (*line == ' ') line++;
  if (*line == '\0') return;
  char *sp = strchr(line, ' ');
  if (sp) { *sp = '\0'; sp++; }
  char *args = sp;

  if (!strcmp(line, "LIGHT"))        handleLight(args);
  else if (!strcmp(line, "PLAY"))    handlePlay(args);
  else if (!strcmp(line, "ALL"))     handleAll(args);
  else if (!strcmp(line, "ATTRACT")) handleAttract(args);
  else if (!strcmp(line, "ARM"))     handleArm(args);
  else if (!strcmp(line, "DISARM"))  handleDisarm();
  else if (!strcmp(line, "SELFTEST"))handleSelftest();
  else if (!strcmp(line, "VERSION")) handleVersion();
  else printErr("cmd");
}

static void pollButtons() {
  uint32_t now = millis();
  for (uint8_t i = 0; i < 4; i++) {
    bool reading = (digitalRead(BTN_PINS[i]) == LOW);  // active low
    if (reading != btn[i].lastReading) {
      btn[i].lastReading = reading;
      btn[i].lastChangeMs = now;
    } else if (now - btn[i].lastChangeMs >= DEBOUNCE_MS &&
               btn[i].stable != reading) {
      btn[i].stable = reading;
      // Always emit BTN/REL so MPU can detect hold combos in any state.
      Serial.print(reading ? "BTN " : "REL ");
      Serial.print(COLOR_CHARS[i]);
      Serial.print(' ');
      Serial.println(now);
      // Inactive-color rejection blink only while armed.
      if (reading && inputMode == IM_ARMED && !armedColors[i]) {
        pulseLed(i, 50);
      }
    }
  }
}

static void updatePulses() {
  uint32_t now = millis();
  for (uint8_t i = 0; i < 4; i++) {
    if (pulse[i].offAtMs && now >= pulse[i].offAtMs) {
      // Only turn off if we are not in steady-on (sequence playback / attract / all-on)
      if (!seqActive && !attractOn) setLed(i, false);
      pulse[i].offAtMs = 0;
    }
  }
}

static void updateSequence() {
  if (!seqActive) return;
  uint32_t now = millis();
  uint32_t dur = seqPhaseOn ? seqOnMs : seqOffMs;
  if (now - seqPhaseStartMs < dur) return;

  int8_t ci = colorIndex(seqColors[seqIdx]);
  if (seqPhaseOn) {
    if (ci >= 0) setLed((uint8_t)ci, false);
    seqPhaseOn = false;
    seqPhaseStartMs = now;
    seqIdx++;
    if (seqIdx >= seqLen) {
      seqActive = false;
      Serial.println("SEQDONE");
      return;
    }
  } else {
    int8_t nci = colorIndex(seqColors[seqIdx]);
    if (nci >= 0) setLed((uint8_t)nci, true);
    seqPhaseOn = true;
    seqPhaseStartMs = now;
  }
}

static void updateAttract() {
  if (!attractOn) return;
  uint32_t now = millis();
  if (now - attractStepMs < 1000) return;
  setLed(attractIdx, false);
  attractIdx = (attractIdx + 1) % 4;
  setLed(attractIdx, true);
  attractStepMs = now;
}

static void updateArmTimeout() {
  if (inputMode == IM_ARMED && millis() >= armDeadlineMs) {
    inputMode = IM_DISARMED;
  }
}

static void readSerial() {
  while (Serial.available()) {
    int c = Serial.read();
    if (c < 0) break;
    if (c == '\r') continue;
    if (c == '\n') {
      rxBuf[rxLen] = '\0';
      if (rxLen > 0) dispatch(rxBuf);
      rxLen = 0;
    } else if (rxLen < sizeof(rxBuf) - 1) {
      rxBuf[rxLen++] = (char)c;
    } else {
      rxLen = 0;  // overflow; drop
    }
  }
}

void setup() {
  Serial.begin(115200);
  for (uint8_t i = 0; i < 4; i++) {
    pinMode(BTN_PINS[i], INPUT_PULLUP);
    pinMode(LED_PINS[i], OUTPUT);
    setLed(i, false);
    btn[i].stable = false;
    btn[i].lastReading = false;
    btn[i].lastChangeMs = 0;
  }
}

void loop() {
  readSerial();
  pollButtons();
  updateSequence();
  updateAttract();
  updatePulses();
  updateArmTimeout();
}
