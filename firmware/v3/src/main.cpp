// SurgeryBox V3 hardware API. No training logic, millimetre conversion or WiFi.
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <Wire.h>
#include <Servo.h>
#include "brake_ramp.h"
#include <stdarg.h>
extern "C" {
#include <user_interface.h>
}

static HardwareSerial& uart=Serial;
static String bootId;
static uint32_t requestId=0, droppedFrames=0;
static bool requestError=false;
static bool suppressReplies=false;
static constexpr uint8_t TX_CAPACITY=16;
static String outbox[TX_CAPACITY];
static uint8_t txHead=0, txCount=0;
static size_t txOffset=0;

// All output is queued: large STATUS responses must never block encoder guards.
class HardwareReplies {
public:
    void println(const char* line) {
        if (suppressReplies) return;
        if (strncmp(line,"ERROR:",6)==0) requestError=true;
        if (txCount>=TX_CAPACITY) { ++droppedFrames; return; }
        String frame=requestId ? "@"+String(requestId) : "!";
        frame+=' '; frame+=bootId; frame+=' '; frame+=line; frame+='\n';
        outbox[(txHead+txCount)%TX_CAPACITY]=frame; ++txCount;
    }
    void printf(const char* fmt,...) {
        char text[512]; va_list args; va_start(args,fmt);
        const int n=vsnprintf(text,sizeof(text),fmt,args); va_end(args);
        if (n<0 || n>=int(sizeof(text))) { println("ERROR: response_overflow"); return; }
        for (char* p=text; *p; ++p) if (*p=='\n' || *p=='\r') *p=0;
        println(text);
    }
} replies;

#define Serial replies
#include "encoder_runtime.h"
#include "motor_runtime.h"
#undef Serial

static Servo brake;
static BrakeRamp brakeRamp;
static uint32_t lastContact=0, lastMotion=0;
static uint32_t lastDiscovery=0;
static uint32_t busClearCount=0;
static int64_t motionAnchor=0;
static bool preparing=false;
static String pendingKind;
static uint32_t pendingToken=0, pendingKeep=0;
static uint32_t seenIds[16]={0};
static uint8_t seenAt=0;

static bool busy() { return preparing || probeActive; }
static void disableBrake() {
    brakeRamp.cancel();
    if (brake.attached()) { sample(); brake.detach(); sample(); }
}
static void systemReport() {
    replies.printf("SYSTEM:uptime_ms=%lu,free_heap=%u,dropped_frames=%lu,host_timeout_ms=1000,motor_lease_ms=250",
        static_cast<unsigned long>(millis()),ESP.getFreeHeap(),static_cast<unsigned long>(droppedFrames));
}
static void brakeReport() {
    replies.printf("BRAKE:enabled=%u,angle=%d,release=180,weak=120,lock=50,settled=%u,measured=0,target=%d,moving=%u,step_ms=20,speed_deg_s=75",
        brake.attached(),brakeRamp.current,brake.attached() && brakeRamp.settled(millis()),
        brakeRamp.target,brake.attached() && brakeRamp.moving());
}
static void encoderReport() { report(); }
static void motorReport() {
    probeReport();
    replies.printf("JOB:preparing=%u,token=%lu,kind=%s",preparing,
        static_cast<unsigned long>(preparing ? pendingToken : probeId),preparing ? pendingKind.c_str() : probeReleasing ? "release" : probeActive ? "wind" : "idle");
}
static void lightReport() { replies.printf("LIGHT:state=%s,D3=%u,gpio=5",digitalRead(D3)?"ON":"OFF",digitalRead(D3)); }
static void stopMotor(const char* reason) {
    preparing=false; pendingKind=""; probeOff(reason);
}
static void safeOff(const char* reason) {
    stopMotor(reason); digitalWrite(D3,LOW); streaming=false;
    disableBrake();
}
static void setBrake(int angle) {
    // Resume the last commanded pulse, then slew to the new target.
    // On first attach this is 180 degrees; the physical position is unknown.
    if (!brake.attached()) { brake.write(brakeRamp.current); brake.attach(D2); }
    brakeRamp.begin(angle,millis());
}
static void serviceBrake() {
    if (brake.attached() && brakeRamp.update(millis())) brake.write(brakeRamp.current);
}
static bool homeReady() {
    return probeFresh() && probeHome.valid;
}
static void startPrepared() {
    const uint32_t token=pendingToken;
    const bool release=pendingKind=="release";
    preparing=false;
    probeId=token;
    probeKeepTime=pendingKeep; // A state transition must not renew the host lease.
    if (release || probe_policy::reachedHome(physicalTicks,probeHome.position)) {
        probeBeginRelease(token);
    } else {
        probeBeginWind(token);
    }
}
static void servicePrepared() {
    if (!preparing) return;
    const uint32_t now=millis();
    if (!homeReady()) {
        stopMotor("prepare_encoder_or_home_fault"); probeReportPending=true; return;
    }
    if (now-pendingKeep>=probe_policy::holdLeaseMs) {
        stopMotor("prepare_keepalive_lost"); probeReportPending=true; return;
    }
    if (!brake.attached()) { stopMotor("prepare_brake_disabled"); probeReportPending=true; return; }
    if (brakeRamp.settled(now)) startPrepared();
}
static bool parseToken(const String& cmd,size_t offset,uint32_t& token) {
    return probe_policy::parseId(cmd.c_str()+offset,token);
}
static void dispatch(const String& cmd) {
    if (cmd=="HELLO") {
        replies.printf("HELLO:product=SurgeryBoxV3,api=1,firmware=3.1.0,protocol=8,boot=%s,transport=usb_serial,baud=115200",bootId.c_str());
        return;
    }
    if (cmd=="INFO?") {
        replies.println("PINS:board=WEMOS_D1_R1,servo=D2_GPIO16,light=D3_GPIO5,mode=D4_GPIO4,sda=D5_GPIO14,scl=D6_GPIO12,in1=D7_GPIO13,in2=D8_GPIO0");
        replies.println("UNITS:encoder=MT6701_I2C14,ticks_per_turn=16384,distance_calibrated=0");
        probeCaps(); systemReport(); return;
    }
    if (cmd=="CAPS?") { probeCaps(); return; }
    if (cmd=="BUS?") {
        replies.printf("BUS:mode=%u,sda=%u,scl=%u,addr=%u,clears=%lu",digitalRead(D4),digitalRead(D5),digitalRead(D6),address,static_cast<unsigned long>(busClearCount));
        return;
    }
    if (cmd=="STATUS?") { encoderReport(); motorReport(); brakeReport(); lightReport(); systemReport(); return; }
    if (cmd=="ENC?") { encoderReport(); return; }
    if (cmd=="MOTOR?" || cmd=="TRAVEL?") { motorReport(); return; }
    if (cmd=="BRAKE?") { brakeReport(); return; }
    if (cmd=="LIGHT?") { lightReport(); return; }
    if (cmd=="STOP" || cmd=="MS") { stopMotor("stopped"); motorReport(); return; }
    if (cmd=="SAFE") { safeOff("safe_off"); motorReport(); brakeReport(); lightReport(); return; }
    if (cmd.startsWith("KEEP:")) {
        uint32_t token=0;
        if (parseToken(cmd,5,token) && preparing && token==pendingToken && millis()-pendingKeep<probe_policy::holdLeaseMs)
            pendingKeep=millis();
        else probeCommand(cmd);
        return;
    }
    if (cmd=="LIGHT:ON" || cmd=="LIGHT:OFF") { probeCommand(cmd); return; }
    if (cmd=="BRAKE:OFF") {
        stopMotor("brake_output_disabled"); disableBrake(); brakeReport(); return;
    }
    if (cmd.startsWith("MOTOR:FINISH:")) {
        uint32_t token=0;
        if (!parseToken(cmd,13,token)) { replies.println("ERROR: invalid_token"); return; }
        if (preparing && token==pendingToken) {
            pendingKind="release";
            replies.printf("ACCEPTED:token=%lu,kind=release",static_cast<unsigned long>(token));
        } else probeCommand("FINISH:"+String(token));
        return;
    }
    if (busy()) { replies.println("ERROR: motor_busy_use_STOP"); return; }
    if (cmd=="BRAKE:RELEASE" || cmd=="BRAKE:WEAK" || cmd=="BRAKE:LOCK") {
        setBrake(cmd=="BRAKE:RELEASE" ? 180 : cmd=="BRAKE:WEAK" ? 120 : 50); brakeReport(); return;
    }
    if (cmd.startsWith("BRAKE:ANGLE:")) {
        uint32_t angle=0;
        if (!parseToken(cmd,12,angle) || angle<50 || angle>180 || abs(int(angle)-brakeRamp.current)>5) {
            replies.println("ERROR: angle_50_to_180_max_step_5"); return;
        }
        setBrake(angle); brakeReport(); return;
    }
    if (cmd=="ZERO") {
        sample();
        if (!angleValid || !continuous) { replies.println("ERROR: encoder_tracking_invalid_restart_required"); return; }
        relativeTicks=0; encoderReport(); return;
    }
    if (cmd=="STREAM:ON" || cmd=="STREAM:OFF") {
        streaming=cmd=="STREAM:ON"; replies.printf("STREAM:enabled=%u,interval_ms=100",streaming); return;
    }
    if (cmd.startsWith("BOUND:") || cmd=="BOUNDS:CLEAR") {
        replies.println("ERROR: manual_endpoints_removed_home_is_power_on_position"); return;
    }
    if (cmd.startsWith("MOTOR:WIND:") || cmd.startsWith("MOTOR:RELEASE:")) {
        const bool release=cmd.startsWith("MOTOR:RELEASE:"); uint32_t token=0;
        if (!parseToken(cmd,release ? 14 : 11,token) || !homeReady()) {
            replies.println("ERROR: valid_token_encoder_and_power_on_home_required"); return;
        }
        setBrake(180);
        if (!brake.attached()) { replies.println("ERROR: brake_attach_failed"); return; }
        probeId=token; pendingToken=token; pendingKind=release ? "release" : "wind";
        pendingKeep=millis(); preparing=true;
        replies.printf("ACCEPTED:token=%lu,kind=%s,brake_settle_ms=500,brake_step_ms=20",static_cast<unsigned long>(token),pendingKind.c_str());
        motorReport(); return;
    }
    replies.println("ERROR: unknown_command");
}

static bool isReadOnly(const String& c) {
    return c=="HELLO" || c=="INFO?" || c=="CAPS?" || c=="BUS?" || c=="STATUS?" || c=="ENC?" || c=="MOTOR?" || c=="TRAVEL?" || c=="BRAKE?" || c=="LIGHT?";
}
static bool isAlwaysSafe(const String& c) {
    return c=="STOP" || c=="MS" || c=="SAFE" || c=="LIGHT:OFF" || c=="BRAKE:OFF";
}
static void handleFrame(const String& frame) {
    // Notifications have no response and can never start an actuator.
    if (frame.startsWith("~")) {
        const int space=frame.indexOf(' ');
        if (space<2 || frame.substring(1,space)!=bootId) return;
        const String cmd=frame.substring(space+1);
        if (cmd=="PING") lastContact=millis();
        else if (cmd.startsWith("KEEP:")) { lastContact=millis(); dispatch(cmd); }
        return;
    }
    if (frame=="MS" || frame=="SAFE") {
        // Emergency notifications have no reply. The caller follows with a
        // tagged query, avoiding two complete SAFE snapshots in the TX queue.
        suppressReplies=true; dispatch(frame); suppressReplies=false; return;
    }
    const int first=frame.indexOf(' '), second=frame.indexOf(' ',first+1);
    uint32_t id=0;
    if (!frame.startsWith("@") || first<2 || second<first+2 ||
        !probe_policy::parseId(frame.substring(1,first).c_str(),id)) {
        replies.println("ERROR: framing_use_at_id_boot_command"); return;
    }
    requestId=id; requestError=false;
    const String session=frame.substring(first+1,second), cmd=frame.substring(second+1);
    if (!isReadOnly(cmd) && !isAlwaysSafe(cmd) && session!=bootId) {
        replies.println("ERROR: stale_boot_session");
    } else if (txCount>1 && !isAlwaysSafe(cmd)) {
        replies.println("ERROR: busy_retry_query_only");
    } else {
        bool duplicate=false;
        if (!isReadOnly(cmd) && !isAlwaysSafe(cmd)) {
            for (const uint32_t old:seenIds) if (old==id) duplicate=true;
            if (!duplicate) { seenIds[seenAt]=id; seenAt=(seenAt+1)%16; }
        }
        if (duplicate) replies.println("ERROR: duplicate_mutation_id");
        else { lastContact=millis(); dispatch(cmd); }
    }
    replies.println(requestError ? "END:ERROR" : "END:OK"); requestId=0;
}

static void clearBusIfStuck() {
    // NXP UM10204 3.1.16: up to nine open-drain clocks, followed by STOP.
    // Never push HIGH against a slave. This does not reset encoder zero/EEPROM.
    pinMode(D5,INPUT_PULLUP); pinMode(D6,INPUT_PULLUP); delayMicroseconds(10);
    if (!digitalRead(D6) || digitalRead(D5)) return;
    ++busClearCount;
    for (int i=0;i<9 && !digitalRead(D5);++i) {
        digitalWrite(D6,LOW); pinMode(D6,OUTPUT); delayMicroseconds(10);
        pinMode(D6,INPUT_PULLUP);
        const uint32_t began=micros();
        while (!digitalRead(D6) && micros()-began<1000) delayMicroseconds(1);
        if (!digitalRead(D6)) return;
        delayMicroseconds(10);
    }
    digitalWrite(D6,LOW); pinMode(D6,OUTPUT);
    digitalWrite(D5,LOW); pinMode(D5,OUTPUT); delayMicroseconds(10);
    pinMode(D6,INPUT_PULLUP); delayMicroseconds(10);
    if (digitalRead(D6)) pinMode(D5,INPUT_PULLUP);
}

void setup() {
    digitalWrite(D7,LOW); pinMode(D7,OUTPUT); digitalWrite(D8,LOW); pinMode(D8,OUTPUT);
    digitalWrite(D3,LOW); pinMode(D3,OUTPUT); pinMode(D2,INPUT);
    digitalWrite(D4,HIGH); pinMode(D4,OUTPUT);
    uart.begin(115200); WiFi.persistent(false); WiFi.mode(WIFI_OFF);
    bootId=String(ESP.getChipId(),HEX)+"-"+String(os_random(),HEX);
    delay(50); // Proven MT6701 MODE/CSN settling interval from the bring-up reader.
    clearBusIfStuck();
    Wire.begin(D5,D6); Wire.setClock(100000); Wire.setClockStretchLimit(1000);
    address=probe(0x06) ? 0x06 : probe(0x46) ? 0x46 : 0;
    input.reserve(160); lastContact=lastMotion=millis(); sample();
    replies.println("READY:SurgeryBoxV3,api=1,outputs=off,home_source=power_on");
}

void loop() {
    probeUpdate(); serviceBrake(); servicePrepared();
    const uint32_t now=millis();
    if ((!address || !angleValid) && !busy() && now-lastDiscovery>=1000) {
        lastDiscovery=now;
        clearBusIfStuck();
        Wire.begin(D5,D6); Wire.setClock(100000); Wire.setClockStretchLimit(1000);
        address=probe(0x06) ? 0x06 : probe(0x46) ? 0x46 : 0;
    }
    if (now-lastAttempt>=SAMPLE_MS) {
        lastAttempt=now; sample();
        if (physicalTicks-motionAnchor>=4 || motionAnchor-physicalTicks>=4) { motionAnchor=physicalTicks; lastMotion=millis(); }
    }
    if (preparing && !homeReady()) {
        stopMotor("prepare_encoder_or_home_fault"); probeReportPending=true;
    }
    if (now-lastContact>=1000 && (busy() || brake.attached() || digitalRead(D3))) {
        safeOff("host_watchdog"); probeReportPending=true;
    }
    if (probeReportPending && txCount<3) probeReport();
    for (int n=0;n<48 && uart.available();++n) {
        const char c=uart.read();
        if (c=='\r') continue;
        if (c=='\n') {
            if (discardLine) replies.println("ERROR: request_too_long");
            else if (input.length()) handleFrame(input);
            input=""; discardLine=false; break;
        }
        if (!discardLine) {
            if (input.length()>=160) { input=""; discardLine=true; }
            else input+=c;
        }
    }
    if (streaming && now-lastReport>=100 && txCount<2) { lastReport=now; encoderReport(); }
    if (txCount) {
        const size_t remaining=outbox[txHead].length()-txOffset;
        const size_t count=min(size_t(max(0,uart.availableForWrite())),min(size_t(64),remaining));
        if (count) txOffset+=uart.write(reinterpret_cast<const uint8_t*>(outbox[txHead].c_str()+txOffset),count);
        if (txOffset==outbox[txHead].length()) { outbox[txHead]=""; txOffset=0; txHead=(txHead+1)%TX_CAPACITY; --txCount; }
    }
    delay(1);
}
