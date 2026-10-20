#pragma once
#include <stdint.h>

// Native scene time is an opaque replay coordinate, NOT milliseconds.
// All duration and stagger decisions use GetTickCount64's monotonic real ms.
// Native time is used only for restart/replay transitions, never show length.
struct PyroSceneSample {
    uintptr_t source=0;
    uint64_t time=0;
    bool valid=false,replay=false;
};
struct PyroSceneClock {
    PyroSceneSample previous;
    uint64_t elapsed=0,wall=0;
    bool blocked=false;
    void begin(const PyroSceneSample& sample,uint64_t now) {
        *this=PyroSceneClock{};previous=sample;wall=now;
    }
    void advance(const PyroSceneSample& sample,uint64_t now,bool hold) {
        if(!hold && !blocked && !sample.replay && !previous.replay && now>=wall)elapsed+=now-wall;
        previous=sample;wall=now;blocked=hold;
    }
};
struct PyroSceneRestart {
    PyroSceneSample previous;
    uint64_t pending=0;
    bool suppressed=true;
    bool sample(const PyroSceneSample& current,bool allow,bool zero,uint64_t now) {
        const bool rewind=allow && !suppressed && zero && current.valid && previous.valid &&
            !current.replay && !previous.replay && current.time<=2000 && previous.time>current.time+500;
        previous=current;suppressed=!allow || !current.valid || current.replay;
        if(suppressed || !zero || current.time>4000) {pending=0;return false;}
        if(rewind)pending=now;
        if(pending && now>=pending && now-pending>=500) {pending=0;return true;}
        return false;
    }
};
