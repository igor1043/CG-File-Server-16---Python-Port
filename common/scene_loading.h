#pragma once
#include <cstdint>
#include <algorithm>
#include <cmath>
namespace scene_loading {
struct Status {
 uint32_t size=sizeof(Status),version=1,club=0,visible=0,ready=0,loaded=0,total=0,variant=0,error=0;
 uint64_t elapsedMs=0;
};
inline float progress(const Status&s){
 if(s.ready)return 1.f;
 if(!s.total)return -1.f;
 return std::min(.99f,float(std::min(s.loaded,s.total))/s.total);
}
inline const char* backgroundParameter(bool ready){return ready?"server16_frontend_clear":"BOOTFLOW";}
inline int secondsRemaining(const Status&s){
 if(s.ready)return 0;
 if(!s.total||!s.loaded||s.elapsedMs<500)return -1;
 if(s.loaded>=s.total)return 0;
 return int(std::min(86400.,std::ceil(double(s.elapsedMs)/1000.*double(s.total-s.loaded)/double(s.loaded))));
}
}
