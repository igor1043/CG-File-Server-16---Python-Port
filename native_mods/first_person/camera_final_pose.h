#pragma once
#include <cmath>
#include <cstring>
#include <initializer_list>
namespace fp {
inline bool finiteCameraData(const float* p){
    for(int i:{0,1,2,4,5,6,12,13,14,16,17})if(!std::isfinite(p[i]))return false;
    return std::fabs(p[0])<20000.f&&std::fabs(p[2])<20000.f&&p[1]>10.f&&p[1]<1000.f;
}
inline void applyFinalPose(float* destination,const float* source){
    // The remaining CameraData words belong to the native clipping/lens ABI.
    for(int i:{0,1,2,4,5,6,12,13,14,16,17})destination[i]=source[i];
}
inline void clearNativeCameraEffects(unsigned char* module){
    module[0x141]=1; // dofForceOff
    module[0x158]=1; // motionBlurForceOffCamera
    module[0x159]=1; // motionBlurForceOffBall
    module[0x15a]=1; // motionBlurForceOffPlayers
}
}
