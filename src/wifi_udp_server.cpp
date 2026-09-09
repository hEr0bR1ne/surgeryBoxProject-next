#include "wifi_udp_server.h"
#include "servo_brake.h"
#include "motor.h"
#include "events.h"
#include "encoder.h"
#include "imu_bridge.h"
#include "config.h"
#include "blood_light.h"

static String readDigitalPinsSnapshot() {
    const uint8_t pins[] = {D0, D1, D2, D3, D4, D5, D6, D7, D8};
    const char* names[] = {"D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"};
    String out = "PINS:";
    for (size_t i = 0; i < sizeof(pins) / sizeof(pins[0]); ++i) {
        if (i > 0) out += ",";
        out += names[i];
        out += "=";
        out += String(digitalRead(pins[i]));
    }
    return out;
}

static String readEncoderSnapshot() {
    return "ENC:raw=" + String(readRawTicks()) +
           ",ticks=" + String(readTicks()) +
           ",dist_m=" + String(readDistance(), 4) +
           ",A=" + String(readEncoderPinA()) +
           ",B=" + String(readEncoderPinB()) +
           ",edgeA=" + String(readEncoderEdgesA()) +
           ",edgeB=" + String(readEncoderEdgesB()) +
           ",seq=" + String(sequenceRunning ? 1 : 0);
}

static const unsigned long ENCODER_TELEMETRY_INTERVAL_MS = 200;
static unsigned long lastTelemetrySendMs = 0;
static unsigned long lastTelemetrySampleMs = 0;
static float lastTelemetryDistanceM = 0.0f;

void resetEncoderTelemetryClock() {
    unsigned long now = millis();
    lastTelemetrySendMs = 0;
    lastTelemetrySampleMs = now;
    lastTelemetryDistanceM = readDistance();
}

void sendEncoderTelemetry(bool force) {
    if (!sequenceRunning) return;

    unsigned long now = millis();
    if (!force && lastTelemetrySendMs != 0 &&
        now - lastTelemetrySendMs < ENCODER_TELEMETRY_INTERVAL_MS) {
        return;
    }

    float dist = readDistance();
    float dt = lastTelemetrySampleMs ? (now - lastTelemetrySampleMs) / 1000.0f : 0.0f;
    float speed = dt > 0.0f ? (dist - lastTelemetryDistanceM) / dt : 0.0f;

    lastTelemetrySampleMs = now;
    lastTelemetryDistanceM = dist;
    lastTelemetrySendMs = now;

    sendUDPMessageToLast("POS:" + String(dist * 100.0f, 2));
    sendUDPMessageToLast("SPEED:" + String(speed * 100.0f, 2));
}

WiFiUDP Udp;
uint16_t localPort;
IPAddress lastRemoteIp;
uint16_t lastRemotePort;
char packetBuffer[255];
ESP8266WebServer httpServer(80);
static String serialCommandBuffer = "";

static bool readIncomingUDP(String &msg) {
    int packetSize = Udp.parsePacket();
    if (!packetSize) return false;
    lastRemoteIp = Udp.remoteIP();
    lastRemotePort = Udp.remotePort();
    int len = Udp.read(packetBuffer, sizeof(packetBuffer) - 1);
    if (len > 0) packetBuffer[len] = '\0';
    msg = String(packetBuffer);
    msg.trim();
    return true;
}

static bool readIncomingSerial(String &msg) {
    while (Serial.available()) {
        char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            serialCommandBuffer.trim();
            if (serialCommandBuffer.length() > 0) {
                msg = serialCommandBuffer;
                serialCommandBuffer = "";
                return true;
            }
            serialCommandBuffer = "";
        } else if (isPrintable(c)) {
            serialCommandBuffer += c;
            if (serialCommandBuffer.length() > 120) {
                serialCommandBuffer = "";
            }
        }
    }
    return false;
}

static bool readIncomingCommand(String &msg) {
    if (!readIncomingUDP(msg) && !readIncomingSerial(msg)) return false;
    // Light commands must not terminate a pending OK/OK1/OK2 or pull wait.
    if (handleBloodLightCommand(msg)) return false;
    if (handleBrakeCalibrationCommand(msg)) return false;
    if (handleMotorSafetyCommand(msg)) return false;
    return true;
}

static bool handleRuntimeControlCommand(const String& msg) {
    if (handleMotorSafetyCommand(msg)) return true;
    if (msg == "Stop") {
        motorAbortWindBack();
        servoBrakeLock();
        sendUDPMessageToLast("ACK: Stop");
        return true;
    }
    if (msg == "Winding") {
        motorStartWindBack();
        sendUDPMessageToLast(motorIsWindingBack() ? "ACK: Winding" : "ERROR: Winding rejected; query TRAVEL?");
        return true;
    }
    if (msg == "MF" || msg == "MotorForward") {
        motorAbortWindBack();
        servoBrakeRelease();
        motorForward();
        sendUDPMessageToLast("ERROR: direct motor drive disabled; use guarded commands");
        return true;
    }
    if (msg == "MR" || msg == "MotorReverse") {
        motorAbortWindBack();
        servoBrakeRelease();
        motorReverse();
        sendUDPMessageToLast("ERROR: direct motor drive disabled; use guarded commands");
        return true;
    }
    if (msg == "MS" || msg == "MotorStop") {
        motorStop();
        sendUDPMessageToLast("ACK: MotorStop");
        return true;
    }
    if (msg == "BR" || msg == "BrakeRelease") {
        servoBrakeRelease();
        sendUDPMessageToLast("ACK: BrakeRelease");
        return true;
    }
    if (msg == "BL" || msg == "BrakeLock") {
        servoBrakeLock();
        sendUDPMessageToLast("ACK: BrakeLock");
        return true;
    }
    if (msg == "BW" || msg == "BrakeWeak") {
        servoBrakeWeak();
        sendUDPMessageToLast("ACK: BrakeWeak");
        return true;
    }
    if (msg == "ENC" || msg == "ENC?") {
        sendUDPMessageToLast(readEncoderSnapshot());
        return true;
    }
    if (msg == "ZERO" || msg == "RSTENC" || msg == "RESET_ENC") {
        if (motorIsWindingBack()) {
            sendUDPMessageToLast("ERROR: ZERO requires idle motor");
            return true;
        }
        resetEncoderDiagnostics();
        sendUDPMessageToLast("ACK: ZERO");
        sendUDPMessageToLast(readEncoderSnapshot());
        return true;
    }
    if (msg == "PINS" || msg == "PINS?") {
        sendUDPMessageToLast(readDigitalPinsSnapshot());
        return true;
    }
    return false;
}

void initWiFiHotspotUDP(const char* ssid, const char* password, uint16_t listenPort) {
    WiFi.softAP(ssid, password);
    localPort = listenPort;
    Udp.begin(localPort);
    Serial.printf("[WiFi UDP] Hotspot started. SSID=%s, Port=%u\n", ssid, localPort);
    Serial.print("[WiFi UDP] Board IP: ");
    Serial.println(WiFi.softAPIP());
}

void initHttpEchoServer() {
    httpServer.on("/echo", HTTP_ANY, []() {
        String body = httpServer.arg("plain");
        Serial.printf("[HTTP] /echo received (%d bytes): %s\n", body.length(), body.c_str());
        httpServer.send(200, "text/plain", body);
    });
    httpServer.onNotFound([]() { httpServer.send(404, "text/plain", "Not Found"); });
    httpServer.begin();
    Serial.println("[HTTP] Echo server started on port 80");
}

void handleHttpServer() {
    httpServer.handleClient();
}

void handleUDPMessages() {
    String msg;
    if (!readIncomingUDP(msg)) return;

    Serial.printf("[WiFi UDP] Received from %s:%u : %s\n",
                  lastRemoteIp.toString().c_str(),
                  lastRemotePort,
                  msg.c_str());

    handleHardwareCommand(msg, true);
}

void handleSerialHardwareCommands() {
    String msg;
    while (readIncomingSerial(msg)) {
        Serial.printf("[Serial CMD] Received: %s\n", msg.c_str());
        handleHardwareCommand(msg, true);
    }
}

void handleHardwareCommand(const String& rawMsg, bool echo) {
    String msg = rawMsg;
    msg.trim();
    if (msg.length() == 0) return;
    if (handleBloodLightCommand(msg)) return;
    if (handleBrakeCalibrationCommand(msg)) return;

    if (echo) {
        sendUDPMessageToLast(msg);
    }

    if (msg == "Start") {
        if (motorIsWindingBack()) {
            sendUDPMessageToLast("ERROR: Start requires idle motor");
            return;
        }
        startEventSequence();
        sendUDPMessageToLast("ACK: Start");
    } else if (handleRuntimeControlCommand(msg)) {
        return;
    } else {
        sendUDPMessageToLast("ACK: " + msg);
    }
}

void sendUDPMessage(const IPAddress& ip, uint16_t port, const String& msg) {
    Serial.printf("[WiFi UDP] Send to %s:%u : %s\n", ip.toString().c_str(), port, msg.c_str());
    Udp.beginPacket(ip, port);
    Udp.write(msg.c_str());
    Udp.endPacket();
}

void sendUDPMessageToLast(const String& msg) {
    Serial.println(msg);
    if (lastRemoteIp) {
        sendUDPMessage(lastRemoteIp, lastRemotePort, msg);
    }
}

void sendSignal(const String& sig) {
    sendUDPMessageToLast(sig);
    Serial.printf("[WiFi UDP] Signal sent: %s\n", sig.c_str());
}

bool waitForCmd(const String& target) {
    while (true) {
        String msg;
        if (readIncomingCommand(msg)) {
            Serial.printf("[WiFi UDP] WaitForCmd got: %s\n", msg.c_str());
            sendUDPMessageToLast(msg);
            if (msg == "Winding") {
                handleRuntimeControlCommand(msg);
                return true;
            }
            if (handleRuntimeControlCommand(msg)) return false;
            if (msg == target) return true;
        }
        motorUpdateWindBack();
        imuBridgeLoop();
        sendEncoderTelemetry(false);
        delay(10);
    }
}

String waitForCmdAny(std::initializer_list<String> targets) {
    while (true) {
        String msg;
        if (readIncomingCommand(msg)) {
            Serial.printf("[WiFi UDP] WaitForCmdAny got: %s\n", msg.c_str());
            sendUDPMessageToLast(msg);
            if (handleRuntimeControlCommand(msg)) return msg;
            for (auto &t : targets) {
                if (msg == t) return msg;
            }
        }
        motorUpdateWindBack();
        imuBridgeLoop();
        sendEncoderTelemetry(false);
        delay(10);
    }
}

void waitShortPull() {
    float startDist = readDistance();
    while (readDistance() < startDist + 0.5) {
        String msg;
        if (readIncomingCommand(msg)) {
            Serial.printf("[WiFi UDP] waitShortPull got: %s\n", msg.c_str());
            sendUDPMessageToLast(msg);
            if (handleRuntimeControlCommand(msg)) return;
        }
        motorUpdateWindBack();
        imuBridgeLoop();
        sendEncoderTelemetry(false);
        delay(10);
    }
}
