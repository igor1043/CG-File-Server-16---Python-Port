#pragma once
#include <cstdint>
#ifdef SERVER16_CAMERA_TEST
static constexpr wchar_t CAMERA_MAPPING_NAME[]=L"Local\\FIFA16_FirstPersonCamera_native_test_v4";
#else
static constexpr wchar_t CAMERA_MAPPING_NAME[]=L"Local\\FIFA16_FirstPersonCamera_v4";
#endif
struct CameraChannel {
    uint32_t version,owner,heartbeat,command,ack,ready;
    int32_t requested,profile,framing;
    int32_t enabled,valid,selected,gameState,error;
    uint32_t frames,applied;
    int32_t fov,look_bias;
    int32_t mode;
    int32_t distance;
};
static_assert(sizeof(CameraChannel)==80,"Server16 camera channel ABI");
