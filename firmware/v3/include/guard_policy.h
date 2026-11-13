#pragma once
#include <stdint.h>
namespace probe_policy {
constexpr int duty=1023;
constexpr uint32_t staleMs=30, holdLeaseMs=250, holdNoProgressMs=500;
constexpr uint32_t holdDurationMs=120000;
constexpr uint32_t releaseMs=1000, releaseWaitMs=50;
constexpr int releaseDelta=128;
// Pulling out increases counts in the current winding orientation.
constexpr int rewindSign=-1;
constexpr int64_t rewindProgress(int64_t position, int64_t reference) {
    return rewindSign * (position - reference);
}
struct HomeReference {
    bool captured=false, valid=false;
    int64_t position=0;
    bool manual=false;
    constexpr void capture(int64_t p) {
        if (!captured) { position=p; captured=true; valid=true; }
    }
    constexpr void invalidate() { valid=false; }
    constexpr void setHere(int64_t p) {
        position=p;
        captured=valid=manual=true;
    }
};
constexpr bool reachedHome(int64_t position,int64_t home,int sign=rewindSign) {
    return sign>0 ? position>=home : position<=home;
}
constexpr bool parseId(const char* p,uint32_t& id) {
    uint32_t n=0;
    if (!*p) return false;
    for (;*p;++p) {
        if (*p<'0' || *p>'9' || n>(2147483647U-uint32_t(*p-'0'))/10) return false;
        n=n*10+uint32_t(*p-'0');
    }
    id=n; return id!=0;
}
enum class Stop { None, Encoder, Home, WrongWay, Timeout, NoProgress, Lease };
constexpr Stop evaluateHome(bool fresh,bool homeValid,int64_t position,int64_t home,
                           int64_t peak,uint32_t elapsed,uint32_t stalled,uint32_t leaseAge,
                           int sign=rewindSign) {
    return !fresh || !homeValid ? Stop::Encoder :
           leaseAge>=holdLeaseMs ? Stop::Lease :
           reachedHome(position,home,sign) ? Stop::Home :
           (sign>0 ? position<=peak-8 : position>=peak+8) ? Stop::WrongWay :
           elapsed>=holdDurationMs ? Stop::Timeout :
           stalled>=holdNoProgressMs ? Stop::NoProgress : Stop::None;
}
enum class Release { Continue, Drive, Complete, Encoder, Lease, Movement };
constexpr Release releaseAction(bool fresh,int64_t p,int64_t start,uint32_t leaseAge,
                                uint32_t elapsed,bool waiting) {
    return !fresh ? Release::Encoder :
           leaseAge>=holdLeaseMs ? Release::Lease :
           p-start>=releaseDelta || start-p>=releaseDelta ? Release::Movement :
           waiting && elapsed>=releaseWaitMs ? Release::Drive :
           !waiting && elapsed>=releaseMs ? Release::Complete : Release::Continue;
}
}
