#pragma once
#include <cstdint>
#include <cstring>

namespace frontend_stadium {
enum class Photograph { Original, Friends, Stadium };
inline bool photographRefreshReady(bool pending,bool ready,int state,uint64_t settled){return !pending&&ready&&(state==0||state==12)&&settled>=500;}
inline Photograph photographPolicy(bool menuPage,bool bootComplete,bool pending,bool ready,bool validRoute,bool transition=false){
    // The native loader temporarily clears the page name. Keep BOOTFLOW during
    // that interval rather than falling back to its profile photograph.
    // Career exit can finish the 3D reload before the next menu exists. Even
    // with no pending request, that gap must not restore the profile photo.
    if(transition||pending)return Photograph::Friends;
    // The active career can have a page ID outside the menu/background list.
    // Once its native route is loaded, still select the stadium component.
    if(ready&&validRoute)return Photograph::Stadium;
    if(menuPage||!bootComplete)return Photograph::Friends;
    return Photograph::Original;
}
using SetProviderString = void(__fastcall*)(void*,const char*,const char*);
inline bool routeRoomPhotograph(void*provider,SetProviderString setter,bool ready){
    if(!provider||!setter)return false;
    // One writer per native factory. The dressing-room hook must not rewrite
    // this same provider after its frontend owner has selected the cover.
    setter(provider,"Param",ready?"server16_frontend_clear":"BOOTFLOW");return true;
}

inline bool routePhotograph(void* provider,SetProviderString setter,const char* imageParameter){
    // Id selects the background component (for example FIFA). Changing Id
    // can prevent that component from loading. Only Param identifies its image.
    if(!provider||!setter||!imageParameter||std::strcmp(imageParameter,"Param"))return false;
    setter(provider,imageParameter,"server16_frontend_clear");
    return true;
}
}
