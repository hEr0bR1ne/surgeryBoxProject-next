#include <Arduino.h>
#include "wifi_udp_server.h"
#include "encoder.h"
#include "servo_brake.h"
#include "motor.h"
#include "events.h"
#include "config.h"
#include "signal_tester.h"
#include "imu_bridge.h"
#include "blood_light.h"

void setup() {
    Serial.begin(115200);
    motorInit();            // Set driver outputs off before WiFi/HTTP startup.
    bloodLightInit();
    Serial.println("[BOOT] SurgeryBox starting...");
    initWiFiHotspotUDP("surgeryBox", "12345678", 4210); // UDP mode
    initHttpEchoServer(); // HTTP /echo endpoint

    //initWiFiHotspot();      // Legacy TCP hotspot
    encoderInit();          // Encoder
    servoBrakeInit();       // Brake servo
    eventsInit();           // Random distance arrays
    signalTesterInit();     // Serial-to-UDP passthrough
    // COM6 is now the primary training-control link. Keep the IMU transparent
    // bridge off here so raw sensor bytes do not corrupt POS/SPEED/Start/OK.
    // imuBridgeInit();     // IMU transparent bridge: sensor -> ESP8266 -> COM3
}

void loop() {
    handleSerialHardwareCommands();

    //handleWiFiCommands();   // Legacy TCP handler
    handleUDPMessages();
    handleHttpServer();
    motorUpdateWindBack();
    processEncoderEvents(); // Check encoder distance and trigger events

    // Periodically log encoder ticks, distance, and speed (only when position changes)
    static unsigned long lastPrint = 0;
    static float lastDist = 0.0f;
    static long lastTicks = 0;
    unsigned long now = millis();
    if (now - lastPrint >= 200) {
        float dist = readDistance();
        float dt = (now - lastPrint) / 1000.0f;
        float speed = dt > 0 ? (dist - lastDist) / dt : 0.0f; // m/s
        long ticks = readTicks();
        lastPrint = now;
        if (ticks != lastTicks) {
            lastTicks = ticks;
            lastDist = dist;
            Serial.printf("[Encoder] ticks=%ld distance=%.3f m speed=%.3f m/s\n",
                          ticks, dist, speed);
        }
    }
    sendEncoderTelemetry(false);

    signalTesterLoop();
    // imuBridgeLoop();
}
