#include "motor.h"
#include "encoder.h"
#include "servo_brake.h"
#include "wifi_udp_server.h"
#include "config.h"
#include "travel_limits.h"

static bool referenced = false;
static bool directionKnown = false;
static bool rewindUsesReverse = true;
static bool active = false;
static bool probing = false;
static bool probeReverse = true;
static long startTicks = 0, bestTicks = 0, lastTicks = 0;
static unsigned long startMs = 0, progressMs = 0, reportMs = 0;
static unsigned long startA = 0, startB = 0;
static unsigned long progressA = 0, progressB = 0;
static long progressTicks = 0;
static int drivePwm = 300;
static const char* reason = "boot_unreferenced";

static void report() {
    sendUDPMessageToLast("TRAVEL:home=" + String(referenced ? 1 : 0) +
        ",pos=" + String(readPhysicalTicks()) + ",low=" + String(TRAVEL_LOW) +
        ",high=" + String(TRAVEL_HIGH) + ",stop=" + String(TRAVEL_STOP) +
        ",direction=" + String(directionKnown ? (rewindUsesReverse ? "R" : "F") : "unknown") +
        ",active=" + String(active ? 1 : 0) + ",pwm=" + String(drivePwm) + ",reason=" + reason);
}

void motorStop() {
    analogWrite(D7, 0);
    analogWrite(D8, 0);
    digitalWrite(D7, LOW);
    digitalWrite(D8, LOW);
    active = false;
}

static void stopWith(const char* why) {
    motorStop();
    reason = why;
    report();
}

void motorInit() {
    pinMode(D7, OUTPUT);
    pinMode(D8, OUTPUT);
    analogWriteRange(1023);
    analogWriteFreq(1000);
    motorStop();
    referenced = false;
    directionKnown = false;
    Serial.println("[Motor] Guarded mode; confirm physical home, then direction probe");
}

static bool begin(bool probe, bool reverse) {
    if (active) { sendUDPMessageToLast("ERROR: motor already active"); return false; }
    const long pos = readPhysicalTicks();
    if (!referenced) { stopWith("home_required"); return false; }
    if (sequenceRunning) { stopWith("idle_training_required"); return false; }
    if (pos <= TRAVEL_STOP || pos > TRAVEL_HIGH) { stopWith("outside_start_range"); return false; }
    if (probe && (pos < PROBE_LOW || pos > PROBE_HIGH)) {
        stopWith("probe_requires_14000_to_20000"); return false;
    }
    if (!probe && !directionKnown) { stopWith("direction_probe_required"); return false; }
    if (probe) directionKnown = false;
    probing = probe;
    probeReverse = reverse;
    startTicks = bestTicks = lastTicks = pos;
    startA = readEncoderEdgesA(); startB = readEncoderEdgesB();
    progressA = startA; progressB = startB; progressTicks = pos;
    startMs = progressMs = reportMs = millis();
    servoBrakeRelease();
    active = true;
    reason = probe ? "probing" : "rewinding";
    // Modest initial PWM; probe and rewind use the same output configuration.
    digitalWrite(reverse ? D7 : D8, LOW);
    analogWrite(reverse ? D8 : D7, drivePwm);
    report();
    return true;
}

// Legacy direct motor commands cannot bypass the travel guard.
void motorForward() { stopWith("manual_drive_disabled_use_probe_or_winding"); }
void motorReverse() { stopWith("manual_drive_disabled_use_probe_or_winding"); }
bool motorIsWindingBack() { return active; }
void motorStartWindBack() { begin(false, rewindUsesReverse); }
void motorWindBack() { motorStartWindBack(); }
void motorAbortWindBack() { stopWith("stopped"); }

void motorUpdateWindBack() {
    if (!active) return;
    const unsigned long now = millis();
    const long pos = readPhysicalTicks();
    const unsigned long edgeA = readEncoderEdgesA(), edgeB = readEncoderEdgesB();
    if ((probing && pos != lastTicks) ||
        (!probing && pos <= progressTicks - 4 && edgeA != progressA && edgeB != progressB)) {
        progressMs = now;
        progressTicks = pos;
        progressA = edgeA; progressB = edgeB;
    }
    lastTicks = pos;
    if (pos < bestTicks) bestTicks = pos;
    const auto action = checkTravel(probing, pos, startTicks, bestTicks, now - startMs, now - progressMs);
    if (action == TravelStop::ProbeDone) {
        motorStop();
        const long delta = pos - startTicks;
        if (abs(delta) >= 8 && readEncoderEdgesA() > startA && readEncoderEdgesB() > startB) {
            rewindUsesReverse = delta < 0 ? probeReverse : !probeReverse;
            directionKnown = true;
            reason = "probe_complete";
        } else {
            directionKnown = false;
            reason = "probe_insufficient_feedback";
        }
        report();
        return;
    }
    if (action != TravelStop::None) {
        if (action == TravelStop::WrongWay || action == TravelStop::NoFeedback) directionKnown = false;
        stopWith(action == TravelStop::Boundary ? "travel_stop" :
                 action == TravelStop::WrongWay ? "wrong_direction" :
                 action == TravelStop::NoFeedback ? "no_encoder_progress" : "timeout");
        return;
    }
    if (now - reportMs >= 200) { reportMs = now; report(); }
}

bool handleMotorSafetyCommand(const String& command) {
    if (command == "TRAVEL?") { report(); return true; }
    if (command.startsWith("MOTOR:PWM:")) {
        if (active || sequenceRunning) {
            sendUDPMessageToLast("ERROR: PWM change requires idle motor and training");
            return true;
        }
        const String value = command.substring(10);
        bool valid = value.length() == 3;
        for (unsigned int i = 0; i < value.length(); ++i) {
            if (value[i] < '0' || value[i] > '9') valid = false;
        }
        const int pwm = value.toInt();
        if (!valid || pwm < 300 || pwm > 700) {
            sendUDPMessageToLast("ERROR: PWM must be an integer from 300 to 700");
            return true;
        }
        motorStop();
        drivePwm = pwm;
        directionKnown = false; // Re-probe using the new drive setting.
        reason = "pwm_set_probe_required";
        report();
        return true;
    }
    if (command == "TRAVEL:HOME") {
        if (active || sequenceRunning) {
            sendUDPMessageToLast("ERROR: home requires idle motor and training");
        } else {
            motorStop();
            confirmPhysicalHome();
            referenced = true;
            directionKnown = false;
            reason = "home_confirmed";
            report();
        }
        return true;
    }
    if (command == "MOTOR:PROBE:R" || command == "MOTOR:PROBE:F") {
        begin(true, command.endsWith(":R"));
        return true;
    }
    if (command.startsWith("TRAVEL:") || command.startsWith("MOTOR:")) {
        sendUDPMessageToLast("ERROR: unsupported guarded motor command");
        return true;
    }
    return false;
}
