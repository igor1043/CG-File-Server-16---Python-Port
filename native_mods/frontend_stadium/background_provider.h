#pragma once
#include <cstring>

namespace frontend_stadium {
enum class Photograph { Original, Friends, Stadium };
inline Photograph photographPolicy(bool menuPage,bool bootComplete,bool pending,bool ready,bool validRoute,bool transition=false){
    // The native loader temporarily clears the page name. That interval must
    // keep the cover too, rather than falling back to its profile photo.
    // Career exit can finish the 3D reload before the next menu exists. Even
    // with no pending request, that gap must not restore the profile photo.
    if(transition)return Photograph::Friends;
    if(menuPage||!bootComplete||pending)
        return menuPage&&ready&&validRoute?Photograph::Stadium:Photograph::Friends;
    return Photograph::Original;
}
using SetProviderString = void(__fastcall*)(void*,const char*,const char*);

inline bool routePhotograph(void* provider,SetProviderString setter,const char* imageParameter){
    // Id selects the background component (for example FIFA). Changing Id
    // can prevent that component from loading. Only Param identifies its image.
    if(!provider||!setter||!imageParameter||std::strcmp(imageParameter,"Param"))return false;
    setter(provider,imageParameter,"server16_frontend_clear");
    return true;
}
}
