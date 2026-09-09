#include "servo_brake.h"
#include <Servo.h>
#include <pins_arduino.h>
#include <HardwareSerial.h>
#include "config.h"
#include "motor.h"
#include "wifi_udp_server.h"

Servo brakeServo;

// User calibration, 2026-09-09: commanded angles, not measured force.
#define BRAKE_LOCK_ANGLE 125
#define BRAKE_WEAK_ANGLE 55
#define BRAKE_RELEASE_ANGLE 0

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
        sendUDPMessageToLast("ERROR: BRAKE expected BRAKE:ANGLE:<0-125>");
        return true;
    }
    String value = command.substring(prefix.length());
    if (value.length() < 1 || value.length() > 3) {
        sendUDPMessageToLast("ERROR: BRAKE angle must be an integer from 0 to 125");
        return true;
    }
    for (unsigned int i = 0; i < value.length(); ++i) {
        if (value[i] < '0' || value[i] > '9') {
            sendUDPMessageToLast("ERROR: BRAKE invalid angle");
            return true;
        }
    }
    int angle = value.toInt();
    if (angle < BRAKE_RELEASE_ANGLE || angle > BRAKE_LOCK_ANGLE) {
        sendUDPMessageToLast("ERROR: BRAKE angle outside 0-125");
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
