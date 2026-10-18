#pragma once
#include <cstdint>
struct CameraPublicState {
    uint32_t version=1,size=sizeof(CameraPublicState);
    int32_t started=0,stopping=0,enabled=0,profile=1,valid=0,selected=-1,gameState=0;
    uint32_t reserved=0;
    int64_t frames=0,applied=0;
};
static_assert(sizeof(CameraPublicState)==56,"Stable external panel protocol");
struct CameraTrackingPublicState {
    uint32_t version=1,size=sizeof(CameraTrackingPublicState);
    int32_t selected=-1,gameState=0,mode=0,valid=0;
    float root[3]{},headEye[3]{},cameraEye[3]{};
    uint32_t headAgeMs=0;
    int64_t frames=0,applied=0;
};
static_assert(sizeof(CameraTrackingPublicState)==80,"Camera tracking diagnostics ABI");
