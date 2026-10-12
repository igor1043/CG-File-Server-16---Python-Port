#pragma once
#include <stdint.h>
// Restart evidence: elapsed-clock rollback to the start, score zero, and no replay UI.
// Does not rely on pointer changes: FIFA can reuse tables and stats on Restart.
struct PyroLifecycle {
    int peak=0;
    uint64_t pending=0,missing=0;
    bool resetReported=false,returnedAfterGap=false,hadScore=false;
    bool sample(bool valid,int clock,int home,int away,bool replay,uint64_t now) {
        if(!valid) { if(!missing)missing=now;return false; }
        const bool gap=missing && now>=missing && now-missing>=1500;
        missing=0;
        if(replay) {pending=0;returnedAfterGap=false;return false;}
        if(gap) {returnedAfterGap=true;resetReported=false;}
        const bool start=clock>=0 && clock<=100 && home==0 && away==0;
        if(start && !resetReported && (peak>100 || returnedAfterGap || hadScore)) {
            if(!pending) {pending=now;return false;}
            if(now>=pending && now-pending>=500) {
                peak=clock;pending=0;resetReported=true;returnedAfterGap=false;hadScore=false;return true;
            }
            return false;
        }
        pending=0;
        if(home>0 || away>0)hadScore=true;
        if(!start)returnedAfterGap=false;
        if(clock>peak)peak=clock;
        if(clock>100)resetReported=false;
        return false;
    }
};
