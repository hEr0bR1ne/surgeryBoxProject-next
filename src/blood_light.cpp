#include "blood_light.h"
#include "wifi_udp_server.h"

// GPIO numbering: GPIO5 is D3 on the configured WEMOS D1 R1.
static constexpr uint8_t BLOOD_LIGHT_PIN = 5;

// User confirmed: the physical MOS module turns on with a HIGH input.
// Override with -DBLOOD_LIGHT_ACTIVE_HIGH=0 for an active-low module.
#ifndef BLOOD_LIGHT_ACTIVE_HIGH
#define BLOOD_LIGHT_ACTIVE_HIGH 1
#endif

static bool lightOn = false;

static void setBloodLight(bool on) {
    digitalWrite(BLOOD_LIGHT_PIN,
                 (on == bool(BLOOD_LIGHT_ACTIVE_HIGH)) ? HIGH : LOW);
    lightOn = on;
}

void bloodLightInit() {
    setBloodLight(false);
    pinMode(BLOOD_LIGHT_PIN, OUTPUT);
    Serial.println("[BloodLight] GPIO5 ready; commanded OFF");
}

bool handleBloodLightCommand(const String& command) {
    if (command == "LIGHT:ON") {
        setBloodLight(true);
    } else if (command == "LIGHT:OFF") {
        setBloodLight(false);
    } else if (command != "LIGHT?") {
        return false;
    }
    // Reports the commanded state; there is no optical feedback sensor.
    sendUDPMessageToLast(lightOn ? "LIGHT:ON" : "LIGHT:OFF");
    return true;
}
