#include "servo_brake.h"
#include <Servo.h>
#include <pins_arduino.h>
#include <HardwareSerial.h>
#include "config.h"
#include "motor.h"
#include "wifi_udp_server.h"

Servo brakeServo;

// V3 user calibration, 2026-11-03: commanded angles, not measured force.
#define BRAKE_LOCK_ANGLE 50
#define BRAKE_WEAK_ANGLE 120
#define BRAKE_RELEASE_ANGLE 180

// Installation may reverse the relationship between angle and brake force.
static constexpr int BRAKE_MIN_ANGLE =
    BRAKE_LOCK_ANGLE < BRAKE_RELEASE_ANGLE ? BRAKE_LOCK_ANGLE : BRAKE_RELEASE_ANGLE;
static constexpr int BRAKE_MAX_ANGLE =
    BRAKE_LOCK_ANGLE > BRAKE_RELEASE_ANGLE ? BRAKE_LOCK_ANGLE : BRAKE_RELEASE_ANGLE;
static_assert(BRAKE_MIN_ANGLE >= 0 && BRAKE_MAX_ANGLE <= 180 &&
              BRAKE_WEAK_ANGLE >= BRAKE_MIN_ANGLE && BRAKE_WEAK_ANGLE <= BRAKE_MAX_ANGLE,
              "Brake calibration must fit the servo range");

static int commandedAngle = BRAKE_RELEASE_ANGLE;

static void writeBrakeAngle(int angle) {
    brakeServo.write(angle);
    commandedAngle = angle;
}

void servoBrakeInit() {
    brakeServo.attach(D2); // GPIO16 on the configured WEMOS D1 R1
    writeBrakeAngle(BRAKE_RELEASE_ANGLE);
    Serial.println("[Servo] Brake initialized");
}

void servoBrakeLock() {
    writeBrakeAngle(BRAKE_LOCK_ANGLE);
    Serial.println("[Servo] Brake locked");
}

void servoBrakeWeak() {
    writeBrakeAngle(BRAKE_WEAK_ANGLE);
    Serial.println("[Servo] Weak damping");
}

void servoBrakeRelease() {
    writeBrakeAngle(BRAKE_RELEASE_ANGLE);
    Serial.println("[Servo] Brake released");
}

bool handleBrakeCalibrationCommand(const String& command) {
    if (command == "BRAKE?") {
        // This is the last requested angle, not measured position or force.
        sendUDPMessageToLast("BRAKE:ANGLE:" + String(commandedAngle));
        return true;
    }
    if (!command.startsWith("BRAKE:")) return false;
    const String prefix = "BRAKE:ANGLE:";
    if (!command.startsWith(prefix)) {
        sendUDPMessageToLast("ERROR: BRAKE expected BRAKE:ANGLE:<50-180>");
        return true;
    }
    String value = command.substring(prefix.length());
    if (value.length() < 1 || value.length() > 3) {
        sendUDPMessageToLast("ERROR: BRAKE angle must be an integer from 50 to 180");
        return true;
    }
    for (unsigned int i = 0; i < value.length(); ++i) {
        if (value[i] < '0' || value[i] > '9') {
            sendUDPMessageToLast("ERROR: BRAKE invalid angle");
            return true;
        }
    }
    int angle = value.toInt();
    if (angle < BRAKE_MIN_ANGLE || angle > BRAKE_MAX_ANGLE) {
        sendUDPMessageToLast("ERROR: BRAKE angle outside 50-180");
        return true;
    }
    if (sequenceRunning || motorIsWindingBack()) {
        sendUDPMessageToLast("ERROR: BRAKE calibration requires idle training and rewind");
        return true;
    }
    // Manual calibration remains limited to five degrees per command.
    if (abs(angle - commandedAngle) > 5) {
        sendUDPMessageToLast("ERROR: BRAKE adjust at most 5 degrees per command");
        return true;
    }
    motorStop();
    writeBrakeAngle(angle);
    sendUDPMessageToLast("BRAKE:ANGLE:" + String(commandedAngle));
    return true;
}
