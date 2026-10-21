#pragma once
#include <cstdint>

namespace frontend_stadium {
// Native command 0x18 takes two bytes. The second bypasses FIFA's comparison
// with the unchanged profile stadium ID when a virtual route changes.
struct ProfileReloadRequest { uint8_t loading=0,force=1; };
static_assert(sizeof(ProfileReloadRequest)==2,"Native profile reload ABI");
template<class Dispatch> bool requestProfileReload(Dispatch dispatch){
    ProfileReloadRequest request;
    dispatch(0x18,&request);
    return request.loading!=0;
}
template<class Dispatch> void profileBackgroundReady(Dispatch dispatch){
    uint8_t unused[16]{};
    dispatch(0x1a,unused);
}

enum class ReloadStep { Wait, Start, BackgroundReady, Failed };
struct ProfileReloadProgress {
    bool started=false,backgroundSent=false,terminal=false;
    unsigned attempts=0;
    uint64_t lastAttempt=0,queuedAt=0;
    void reset(uint64_t now){started=false;backgroundSent=false;terminal=false;attempts=0;lastAttempt=queuedAt=now;}
    void fail(){terminal=true;}
    ReloadStep next(int nativeState,bool prepared,uint64_t now){
        if(terminal||!prepared)return ReloadStep::Wait; // never acknowledge the boot loader
        // Captured failure: state 14 was already accepted, awaiting the image
        // callback. It is not a busy/rejected start and must not be restarted.
        if(nativeState==14){
            started=true;
            if(!backgroundSent&&now-queuedAt>=500){backgroundSent=true;return ReloadStep::BackgroundReady;}
            return ReloadStep::Wait;
        }
        if(started||(nativeState!=0&&nativeState!=12)||now-lastAttempt<500)return ReloadStep::Wait;
        if(attempts>=8){terminal=true;return ReloadStep::Failed;}
        ++attempts;lastAttempt=now;
        return ReloadStep::Start;
    }
};
}
