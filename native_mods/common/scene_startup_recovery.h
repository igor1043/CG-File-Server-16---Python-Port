#pragma once
#include <stdint.h>
#include <stddef.h>

// One additional placement/resource pass at stadium opening. A slow native
// load can use two more passes; a completed pass is never repeated in gameplay.
struct SceneStartupRecovery {
    static constexpr uint64_t windowMs=6000;
    bool openingSeen=false,active=false,pending=false,complete=false,expired=false;
    uint64_t began=0,nextAttempt=0;
    unsigned attempts=0;
    bool poll(uint64_t now,bool known,bool opening,bool suspended) {
        if(active&&now-began>=windowMs){expired=pending;active=false;pending=false;}
        // A pause or an unreadable transitional frame is not a new match.
        if(!known||suspended)return false;
        if(!opening){openingSeen=false;active=false;pending=false;return false;}
        if(!openingSeen){
            openingSeen=true;active=true;pending=complete=expired=false;
            began=now;nextAttempt=now+500;attempts=0;
        }
        if(!active||complete||attempts>=3||now<nextAttempt)return false;
        ++attempts;pending=true;nextAttempt=now+(attempts==1?1000:2000);
        return true;
    }
    bool confirm(bool ready) {
        if(!active||!pending||complete||!ready)return false;
        complete=true;pending=active=false;return true;
    }
};

// Only caller-owned private placements may be passed here. Preserve model
// selection, transforms and all normal actors; let the native builder rebind.
inline void scene_startup_rebind(unsigned char* records,size_t count) {
    for(size_t i=0;i<count;++i){
        auto record=records+i*0x50;
        record[0x40]=record[0x41]=0xff;record[0x45]=0;
    }
}
