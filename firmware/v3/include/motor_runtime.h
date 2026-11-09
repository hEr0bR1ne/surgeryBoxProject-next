#pragma once
#include "guard_policy.h"
static probe_policy::HomeReference probeHome;
static bool probeActive=false,probeHolding=false,probeReleasing=false,probeReleaseWait=false;
static bool probeReportPending=false;
static uint32_t probeId=0,probeKeepTime=0,probeStarted=0,probeProgress=0,probeReleaseAt=0;
static int64_t probeBest=0,probeReleaseStart=0;
static const char* probeReason="boot_disarmed";
static void probeOff(const char* reason) {
    analogWrite(D7,0); analogWrite(D8,0);
    digitalWrite(D7,LOW); digitalWrite(D8,LOW);
    probeActive=probeHolding=probeReleasing=probeReleaseWait=false;
    probeReason=reason;
}
static void probeCaptureHome() { probeHome.capture(physicalTicks); }
static void probeFault() {
    const bool changed=probeHome.valid || probeActive;
    probeOff("encoder_fault_home_invalid"); probeHome.invalidate();
    if (changed) probeReportPending=true;
}
static bool probeFresh() {
    return angleValid && continuous && initialized && millis()-lastGood<=probe_policy::staleMs;
}
static void probeReport() {
    probeReportPending=false;
    Serial.printf("MOTORPROBE:active=%u,pos=%lld,home=%lld,home_valid=%u,home_captured=%u,home_source=power_on,rewind_sign=1,extension_limit=0,deadzone_ticks=0,pwm=%u,D7=%d,D8=%d,protocol=8,encoder_ok=%u,age_ms=%lu,holding=%u,id=%lu,releasing=%u,reason=%s\n",
        probeActive,static_cast<long long>(physicalTicks),static_cast<long long>(probeHome.position),
        probeHome.valid,probeHome.captured,probe_policy::duty,digitalRead(D7),digitalRead(D8),
        probeFresh(),static_cast<unsigned long>(millis()-lastGood),probeHolding,
        static_cast<unsigned long>(probeId),probeReleasing,probeReason);
}
static void probeCaps() {
    Serial.printf("MOTORCAPS:protocol=8,hold_ms=%u,hold_no_progress_ms=%u,lease_ms=%u,pwm=%u,stale_ms=%u,release_ms=%u,release_wait_ms=%u,release_delta=%u,light_gpio=5,home_source=power_on,rewind_sign=1,extension_limit=0,deadzone_ticks=0\n",
        probe_policy::holdDurationMs,probe_policy::holdNoProgressMs,probe_policy::holdLeaseMs,
        probe_policy::duty,probe_policy::staleMs,probe_policy::releaseMs,probe_policy::releaseWaitMs,probe_policy::releaseDelta);
}
static void probeBeginRelease(uint32_t id) {
    probeOff("release_wait");
    probeId=id; probeActive=probeReleasing=probeReleaseWait=true;
    probeReleaseStart=physicalTicks; probeReleaseAt=millis();
    probeReportPending=true;
}
static void probeBeginWind(uint32_t id) {
    probeOff("holding"); probeId=id; probeActive=probeHolding=true;
    probeBest=physicalTicks; probeStarted=probeProgress=millis();
    analogWriteRange(1023); analogWriteFreq(500); analogWrite(D8,probe_policy::duty);
    probeReportPending=true;
}
static void probeUpdate() {
    const uint32_t now=millis();
    if ((probeHome.valid || probeActive) && !probeFresh()) { probeFault(); return; }
    if (!probeActive) return;
    if (probeReleasing) {
        const auto action=probe_policy::releaseAction(probeFresh(),physicalTicks,probeReleaseStart,
            now-probeKeepTime,now-probeReleaseAt,probeReleaseWait);
        const char* stop=nullptr;
        if (action==probe_policy::Release::Encoder) { probeFault(); return; }
        if (action==probe_policy::Release::Lease) stop="release_keepalive_lost";
        else if (action==probe_policy::Release::Movement) stop="release_moved_line";
        else if (action==probe_policy::Release::Drive) {
            probeReleaseWait=false; probeReleaseAt=now; probeReason="releasing_1s";
            analogWriteRange(1023); analogWriteFreq(500); analogWrite(D7,probe_policy::duty);
        } else if (action==probe_policy::Release::Complete) stop="release_complete";
        if (stop) { probeOff(stop); probeReportPending=true; }
        return;
    }
    if (physicalTicks-probeBest>=4) { probeBest=physicalTicks; probeProgress=now; }
    const auto result=probe_policy::evaluateHome(probeFresh(),probeHome.valid,physicalTicks,
        probeHome.position,probeBest,now-probeStarted,now-probeProgress,now-probeKeepTime);
    if (result==probe_policy::Stop::None) return;
    if (result==probe_policy::Stop::Home) { probeBeginRelease(probeId); return; }
    if (result==probe_policy::Stop::Encoder) probeFault();
    else probeOff(result==probe_policy::Stop::Lease ? "hold_keepalive_lost" :
        result==probe_policy::Stop::WrongWay ? "wrong_way" :
        result==probe_policy::Stop::Timeout ? "hold_time_limit" : "no_progress");
    probeReportPending=true;
}
static bool probeCommand(const String& cmd) {
    if (cmd=="LIGHT:ON" || cmd=="LIGHT:OFF") {
        digitalWrite(D3,cmd=="LIGHT:ON" ? HIGH : LOW);
        Serial.printf("LIGHT:state=%s,D3=%u,gpio=5\n",digitalRead(D3)?"ON":"OFF",digitalRead(D3));
        return true;
    }
    if (cmd.startsWith("KEEP:")) {
        uint32_t id=0;
        if (probe_policy::parseId(cmd.c_str()+5,id) && probeActive && id==probeId && probeFresh() &&
            millis()-probeKeepTime<probe_policy::holdLeaseMs) probeKeepTime=millis();
        return true;
    }
    if (cmd.startsWith("FINISH:")) {
        uint32_t id=0;
        if (probe_policy::parseId(cmd.c_str()+7,id) && id==probeId && probeActive && probeFresh() &&
            millis()-probeKeepTime<probe_policy::holdLeaseMs) {
            if (!probeReleasing) probeBeginRelease(id);
            Serial.printf("ACK: FINISH:%lu\n",static_cast<unsigned long>(id));
        } else Serial.println("ERROR: no_matching_rewind_to_finish");
        return true;
    }
    return false;
}
