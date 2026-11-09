#include "../include/guard_policy.h"
#include "../include/brake_ramp.h"
using namespace probe_policy;
static_assert(evaluateHome(true,true,-1,0,-1,10,0,0)==Stop::None,"No early-stop deadzone even one tick from zero");
static_assert(evaluateHome(true,true,0,0,-1,10,0,0)==Stop::Home,"Exact zero ends rewind");
static_assert(evaluateHome(true,true,10,0,-1,10,0,0)==Stop::Home,"A sample crossing zero ends rewind");
static_assert(evaluateHome(true,true,-1000000,0,-1000000,10,0,0)==Stop::None,"No extension-distance cap");
static_assert(evaluateHome(true,true,-300,0,-300,16000,0,0)==Stop::None,"Rewind may exceed old 15-second cap");
static_assert(evaluateHome(true,true,-100,0,-100,120000,0,0)==Stop::Timeout,"Hard run watchdog remains");
static_assert(evaluateHome(false,true,-1,0,-1,10,0,0)==Stop::Encoder,"Lost feedback stops drive");
static_assert(evaluateHome(true,false,-1,0,-1,10,0,0)==Stop::Encoder,"Lost home never starts drive");
static_assert(evaluateHome(true,true,-1,0,-1,10,0,250)==Stop::Lease,"Lost lease stops drive");
static_assert(evaluateHome(true,true,0,0,0,10,0,250)==Stop::Lease,"Lost lease at zero never starts release");
static_assert(evaluateHome(true,true,-100,0,-100,500,500,0)==Stop::NoProgress,"Stall still stops");
static_assert(evaluateHome(true,true,-108,0,-100,100,0,0)==Stop::WrongWay,"Reverse from peak stops");
static_assert(reachedHome(0,0) && !reachedHome(-1,0) && reachedHome(-1,0,-1),"Direction-aware zero crossing");
static_assert(releaseAction(true,0,0,0,49,true)==Release::Continue,"Break before reversing");
static_assert(releaseAction(true,0,0,0,50,true)==Release::Drive,"50ms break");
static_assert(releaseAction(true,-1000000,-1000000,0,50,true)==Release::Drive,"Release has no extension limit");
static_assert(releaseAction(true,0,0,20,999,false)==Release::Continue,"No progress needed for release");
static_assert(releaseAction(true,0,0,20,1000,false)==Release::Complete,"Release ends at one second");
static_assert(releaseAction(true,0,0,250,50,true)==Release::Lease,"Lost link never starts release");
static_assert(releaseAction(false,0,0,0,50,true)==Release::Encoder,"No feedback never starts release");
static_assert(releaseAction(true,128,0,20,100,false)==Release::Movement,"Unexpected line motion stops release");
constexpr bool referenceChecks() {
    HomeReference h; h.capture(0); h.capture(-500);
    if (!h.valid || h.position!=0) return false;
    h.invalidate(); h.capture(-700);
    return h.captured && !h.valid && h.position==0;
}
static_assert(referenceChecks(),"Capture once; faults/reconnection never silently relocate home");
constexpr bool idChecks() {
    uint32_t id=0;
    return parseId("2147483647",id) && id==2147483647 && !parseId("2147483648",id) &&
        !parseId("0",id) && !parseId("-1",id) && !parseId("",id) && !parseId("1x",id);
}
static_assert(idChecks(),"Reject malformed/overflow tokens");
constexpr bool rampChecks() {
    BrakeRamp r; r.begin(120,100);
    if (r.update(119) || !r.update(120) || r.current!=179) return false;
    if (!r.update(140) || r.current!=177) return false;
    for (uint32_t t=160;t<=900;t+=20) r.update(t);
    if (r.current!=120 || r.settled(1399) || !r.settled(1400)) return false;
    r.begin(180,1500); r.update(1520); r.cancel();
    if (r.update(1540) || r.moving() || r.current!=121) return false;
    r.begin(180,1600); r.update(2000);
    if (r.current!=122) return false;
    r.begin(123,0xfffffff0U);
    return r.update(4) && r.current==123 && !r.settled(503) && r.settled(504);
}
static_assert(rampChecks(),"50 percent faster slew, settle interlock, cancel, no catch-up and clock wrap");
