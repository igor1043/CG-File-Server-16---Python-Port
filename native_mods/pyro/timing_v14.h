#pragma once
#include <stdint.h>
static bool pyro_show_expired(uint64_t now,uint64_t start,bool goal,uint64_t duration=0) {
    return now<start || now-start>=(duration?duration:(goal?25000ULL:60000ULL));
}
// Keep the current show and its remaining duration across pause/replay UI.
struct PyroShowPause {
    bool paused=false;
    uint64_t since=0;
    bool enter(uint64_t now) {
        if(paused)return false;
        paused=true;since=now;return true;
    }
    bool resume(uint64_t now,uint64_t& start) {
        if(!paused)return false;
        if(now>=since)start+=now-since;
        paused=false;since=0;return true;
    }
};
