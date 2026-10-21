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
inline void clearNativeCameraEffects(unsigned char* module,bool firstPerson=false){
    module[0x141]=1; // dofForceOff
    module[0x158]=1; // motionBlurForceOffCamera
    module[0x159]=1; // motionBlurForceOffBall
    module[0x15a]=1; // motionBlurForceOffPlayers
    if(firstPerson){
        // Keep a gentler version of the native wide-angle compensation.
        // Removing it entirely exposes extreme rectilinear edge stretching.
        // The stock curve reaches 0.4 / inverse zoom 0.78 at 120 degrees;
        // retain half its correction, without its extra image enlargement.
        // Fixup recomputes these outputs each frame; never alter the native
        // curve or a third-person/menu camera's lens configuration.
        float distortion=0.f;
        std::memcpy(&distortion,module+0x164,sizeof distortion);
        if(std::isfinite(distortion)&&distortion>=0.f){
            distortion=std::fmin(distortion*.5f,.2f);
            const float inverseZoom=1.f;
            std::memcpy(module+0x164,&distortion,sizeof distortion);
            std::memcpy(module+0x168,&inverseZoom,sizeof inverseZoom);
        }
    }
}
}
