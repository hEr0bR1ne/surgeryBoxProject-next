#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <Wire.h>

// WEMOS D1 R1, NOT D1 mini: D4=GPIO4, D5=GPIO14, D6=GPIO12.
static_assert(D4 == 4 && D5 == 14 && D6 == 12, "Requires WEMOS D1 R1 pin mapping");
constexpr uint8_t MODE_SELECT = D4; // Only MT6701 M/MODE and Z/CSN inputs.
constexpr uint8_t DATA_PIN = D5;
constexpr uint8_t CLOCK_PIN = D6;
constexpr uint32_t SAMPLE_MS = 10;
constexpr uint32_t MAX_GAP_MS = 100;

// Multi-turn displacement; first valid sample establishes this boot's home.
constexpr int angleDelta(int current, int previous) {
    return current - previous > 8192 ? current - previous - 16384 :
           current - previous < -8192 ? current - previous + 16384 : current - previous;
}
static_assert(angleDelta(3, 16380) == 7, "Forward zero crossing");
static_assert(angleDelta(16380, 3) == -7, "Reverse zero crossing");
static_assert(angleDelta(200, 100) == 100 && angleDelta(100, 200) == -100,
              "Bidirectional angle delta");

static uint8_t address = 0;
static uint16_t raw = 0;
static bool angleValid = false;
static bool initialized = false;
static bool continuous = false;
static bool streaming = false;
static int64_t relativeTicks = 0;
// Independent from diagnostic ZERO; used by the optional guarded motor test.
static int64_t physicalTicks = 0;
static uint32_t samples = 0, errors = 0, lastGood = 0, lastAttempt = 0, lastReport = 0;
static String input;
static bool discardLine = false;

static void probeFault();
static void probeUpdate();
static void probeCaptureHome();

static bool probe(uint8_t candidate) {
    Wire.beginTransmission(candidate);
    return Wire.endTransmission() == 0;
}

// Datasheet: read 0x03 first, then 0x04, as individual register reads.
// The one-byte write only selects the read register; no configuration is written.
static bool readRegister(uint8_t reg, uint8_t& value) {
    Wire.beginTransmission(address);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(address, uint8_t(1)) != 1) return false;
    value = Wire.read();
    return true;
}

static void sample() {
    const uint32_t now = millis();
    uint8_t high = 0, low = 0;
    if (!address || !readRegister(0x03, high) || !readRegister(0x04, low)) {
        angleValid = false;
        if (initialized) continuous = false; // Do not bridge an unknown movement gap.
        probeFault();
        errors++;
        return;
    }
    const uint16_t current = (uint16_t(high) << 6) | (low >> 2);
    if (!initialized) {
        initialized = true;
        continuous = true;
        relativeTicks = 0;
        physicalTicks = 0;
        probeCaptureHome();
    } else if (continuous) {
        const int delta = angleDelta(current, raw);
        if (now - lastGood > MAX_GAP_MS || delta == 8192 || delta == -8192) {
            continuous = false;
            probeFault();
        } else {
            relativeTicks += delta;
            physicalTicks += delta;
        }
    }
    raw = current;
    lastGood = now;
    samples++;
    angleValid = true;
    probeUpdate();
}

static void report() {
    const uint32_t age = initialized ? millis() - lastGood : 0;
    Serial.printf("I2CENC:addr=0x%02X,valid=%u,raw14=%u,angle_deg=%.4f,relative_valid=%u,relative_ticks=%lld,age_ms=%lu,samples=%lu,errors=%lu,mode_pin=%u\n",
                  address, angleValid ? 1 : 0, raw, raw * (360.0 / 16384.0),
                  continuous && angleValid ? 1 : 0, static_cast<long long>(relativeTicks),
                  static_cast<unsigned long>(age), static_cast<unsigned long>(samples),
                  static_cast<unsigned long>(errors), digitalRead(MODE_SELECT));
}
