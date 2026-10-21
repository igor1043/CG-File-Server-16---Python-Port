#pragma once
#include <cstdint>
namespace fp {
class CameraSubject {
    uintptr_t context=0;
    int pinned=-1;
public:
    void reset(){context=0;pinned=-1;}
    int resolve(uintptr_t owner,int nativeSelected,bool usersLocked){
        if(owner!=context){context=owner;pinned=-1;}
        if(!usersLocked){pinned=-1;return nativeSelected;}
        if(pinned<0&&nativeSelected>=0&&nativeSelected<46)pinned=nativeSelected;
        // A missing pose suspends the mod; it never silently adopts another player.
        return pinned;
    }
};
}
