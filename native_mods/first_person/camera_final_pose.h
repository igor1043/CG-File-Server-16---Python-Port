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
struct Lens {float distortion,inverseZoom;};
inline Lens firstPersonLens(float nativeDistortion){
    const float wanted=std::fmin(nativeDistortion*.5f,.2f);
    // Native standalone and combiner pixel shaders both sample at:
    // q = p * (distortion * length(p) + (1-distortion) * inverseZoom),
    // p in [-1,1]^2. Keep the center derivative (1-wanted) unchanged while
    // ensuring the corner factor stays below one: .7 * sqrt(2) < 1.
    // Unlike changing zoom alone, this does not enlarge the center again.
    const float safeDistortion=wanted*.7f;
    return {safeDistortion,(1.f-wanted)/(1.f-safeDistortion)};
}
inline void clearNativeCameraEffects(unsigned char* module,bool firstPerson=false){
    module[0x141]=1; // dofForceOff
    module[0x158]=1; // motionBlurForceOffCamera
    module[0x159]=1; // motionBlurForceOffBall
    module[0x15a]=1; // motionBlurForceOffPlayers
    if(firstPerson){
        // Fixup recomputes these outputs each frame. The center-preserving
        // pair avoids out-of-range UVs instead of relying on sampler clamping.
        // Never alter the native curve or a third-person/menu lens.
        float distortion=0.f;
        std::memcpy(&distortion,module+0x164,sizeof distortion);
        if(std::isfinite(distortion)&&distortion>=0.f){
            const auto lens=firstPersonLens(distortion);
            std::memcpy(module+0x164,&lens.distortion,sizeof lens.distortion);
            std::memcpy(module+0x168,&lens.inverseZoom,sizeof lens.inverseZoom);
        }
    }
}
}
