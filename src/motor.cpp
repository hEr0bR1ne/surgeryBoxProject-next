#include "motor.h"
#include "encoder.h"
#include "servo_brake.h"
#include "wifi_udp_server.h"
#include "config.h"
#include "travel_limits.h"

static bool referenced = false;
static bool directionKnown = false;
static bool rewindUsesReverse = false;
static bool active = false;
static bool probing = false;
static bool probeReverse = true;
static long startTicks = 0, bestTicks = 0, lastTicks = 0;
static unsigned long startMs = 0, progressMs = 0, reportMs = 0;
static unsigned long startA = 0, startB = 0;
static unsigned long progressA = 0, progressB = 0;
static long progressTicks = 0;
static int drivePwm = 300;
static unsigned long probeDurationMs = PROBE_MS;
static int matrixCombination = -1;
static const char* reason = "boot_unreferenced";

static void report() {
    sendUDPMessageToLast("TRAVEL:home=" + String(referenced ? 1 : 0) +
        ",pos=" + String(readPhysicalTicks()) + ",low=" + String(TRAVEL_LOW) +
        ",high=" + String(TRAVEL_HIGH) + ",stop=" + String(TRAVEL_STOP) +
        ",direction=" + String(directionKnown ? (rewindUsesReverse ? "R" : "F") : "unknown") +
        ",active=" + String(active ? 1 : 0) + ",pwm=" + String(drivePwm) +
        ",control=dir_pwm_v1,pwm_mode=same_positive,matrix=1,combo=" + String(matrixCombination) +
        ",duration_ms=" + String(probeDurationMs) + ",reason=" + reason);
}

void motorStop() {
    analogWrite(D7, 0);
    analogWrite(D8, 0);
    digitalWrite(D7, LOW);
    digitalWrite(D8, LOW);
    active = false;
    reason = "stopped";
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
    analogWriteFreq(500);
    motorStop();
    referenced = false;
    directionKnown = false;
    reason = "boot_unreferenced";
    Serial.println("[Motor] Guarded mode; confirm physical home, then direction probe");
}

static bool begin(bool probe, bool reverse, int combination = -1) {
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
    matrixCombination = combination;
    probeReverse = reverse;
    startTicks = bestTicks = lastTicks = pos;
    startA = readEncoderEdgesA(); startB = readEncoderEdgesB();
    progressA = startA; progressB = startB; progressTicks = pos;
    startMs = progressMs = reportMs = millis();
    servoBrakeRelease();
    active = true;
    reason = probe ? "probing" : "rewinding";
    // User-requested comparison: only AIN1 direction changes; AIN2 uses
    // the identical positive PWM value for F and R (no duty inversion).
    // Establish 11 before reverse PWM, avoiding a full reverse start pulse.
    if (combination >= 0) {
        analogWrite(D7, matrixDuty(combination / 3, drivePwm));
        analogWrite(D8, matrixDuty(combination % 3, drivePwm));
    } else if (reverse) {
        digitalWrite(D8, HIGH);
        digitalWrite(D7, HIGH);
    } else {
        digitalWrite(D7, LOW);
    }
    if (combination < 0) analogWrite(D8, motorPwmHighDuty(reverse, drivePwm));
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
    if (matrixCombination >= 0) {
        const auto result = checkMatrix(pos, startTicks, now - startMs, probeDurationMs);
        if (result != TravelStop::None) {
            directionKnown = false;
            stopWith(result == TravelStop::Boundary ? "travel_stop" : "matrix_complete");
        } else if (now - reportMs >= 100) {
            reportMs = now; report();
        }
        return;
    }
    if ((probing && pos != lastTicks) ||
        (!probing && pos <= progressTicks - 4 && edgeA != progressA && edgeB != progressB)) {
        progressMs = now;
        progressTicks = pos;
        progressA = edgeA; progressB = edgeB;
    }
    lastTicks = pos;
    if (pos < bestTicks) bestTicks = pos;
    const auto action = probing
        ? checkJog(probeReverse, pos, startTicks, bestTicks, now - startMs, probeDurationMs)
        : checkTravel(false, pos, startTicks, bestTicks, now - startMs, now - progressMs);
    if (action == TravelStop::ProbeDone) {
        motorStop();
        const long delta = pos - startTicks;
        if (probeReverse) {
            directionKnown = false;
            reason = "clutch_jog_complete";
        } else if (delta <= -8 && readEncoderEdgesA() > startA && readEncoderEdgesB() > startB) {
            rewindUsesReverse = false;
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
                 action == TravelStop::ClutchMoved ? "clutch_unexpected_movement" :
                 action == TravelStop::WrongWay ? "wrong_direction" :
                 action == TravelStop::NoFeedback ? "no_encoder_progress" : "timeout");
        return;
    }
    if (now - reportMs >= 200) { reportMs = now; report(); }
}

bool handleMotorSafetyCommand(const String& command) {
    if (command == "TRAVEL?") { report(); return true; }
    if (command.startsWith("MOTOR:MATRIX:")) {
        const String value = command.substring(15);
        bool valid = command.length() >= 18 && command.charAt(14) == ':' &&
            command.charAt(13) >= '0' && command.charAt(13) <= '8' && value.length() <= 4;
        for (unsigned int i = 0; i < value.length(); ++i)
            if (value[i] < '0' || value[i] > '9') valid = false;
        const long duration = value.toInt();
        if (!valid || duration < 100 || duration > 2000) {
            sendUDPMessageToLast("ERROR: use MOTOR:MATRIX:0..8:100..2000");
        } else if (active) {
            sendUDPMessageToLast("ERROR: motor already active");
        } else {
            const int combination = command.charAt(13) - '0';
            probeDurationMs = matrixDuration(combination, duration);
            begin(true, false, combination);
        }
        return true;
    }
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
    if (command.startsWith("MOTOR:JOG:")) {
        const String value = command.substring(12);
        bool valid = command.length() >= 15 && command.charAt(11) == ':' &&
            (command.charAt(10) == 'F' || command.charAt(10) == 'R') && value.length() <= 4;
        for (unsigned int i = 0; i < value.length(); ++i)
            if (value[i] < '0' || value[i] > '9') valid = false;
        const long duration = value.toInt();
        if (!valid || duration < 100 || duration > 2000) {
            sendUDPMessageToLast("ERROR: use MOTOR:JOG:F:100..2000 or MOTOR:JOG:R:100..2000");
        } else if (active) {
            sendUDPMessageToLast("ERROR: motor already active");
        } else {
            probeDurationMs = duration;
            begin(true, command.charAt(10) == 'R');
        }
        return true;
    }
    if (command == "MOTOR:PROBE:R" || command == "MOTOR:PROBE:F") {
        if (active) { sendUDPMessageToLast("ERROR: motor already active"); return true; }
        probeDurationMs = PROBE_MS;
        begin(true, command.endsWith(":R"));
        return true;
    }
    if (command.startsWith("TRAVEL:") || command.startsWith("MOTOR:")) {
        sendUDPMessageToLast("ERROR: unsupported guarded motor command");
        return true;
    }
    return false;
}
