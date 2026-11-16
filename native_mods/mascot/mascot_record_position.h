#pragma once
#include <string.h>
#include <stdint.h>
#include <initializer_list>

// Native 43af5f9/43af5ff calls 43af190 when mode +43 is zero and
// locomotion +44 is nonzero. That routine writes yaw +1c (43af586),
// which 43af645 copies to +2c after our palette has already been oriented.
// Own this flag only for the reserved mascot, alongside the private pose.
struct MascotNativeMotionOwnership {
    uintptr_t record=0;
    unsigned char locomotion=0;
    bool active=false;
};
inline bool mascot_control_native_motion(unsigned char* record,MascotNativeMotionOwnership& state) {
    if(!record || (state.active && state.record!=(uintptr_t)record))return false;
    if(!state.active){state.record=(uintptr_t)record;state.locomotion=record[0x44];state.active=true;}
    record[0x44]=0;
    const float neutral=0;
    for(unsigned int offset:{0x1cu,0x2cu,0x3cu})memcpy(record+offset,&neutral,sizeof(neutral));
    return true;
}
inline bool mascot_release_native_motion(unsigned char* record,MascotNativeMotionOwnership& state) {
    if(!record || !state.active || state.record!=(uintptr_t)record)return false;
    record[0x44]=state.locomotion;state={};return true;
}

// Native BatchSLE 43a8d87/43a8d8c restores +30 into +20 when its instance
// cache changes. Moving only +20 lets a later resource rebuild undo placement.
inline void mascot_store_position(unsigned char* record,const float position[3]) {
    float copy[3];memcpy(copy,position,sizeof(copy));
    memcpy(record+0x20,copy,sizeof(copy));memcpy(record+0x30,copy,sizeof(copy));
}
inline void mascot_restore_positions(unsigned char* record,const float current[3],const float stored[3]) {
    memcpy(record+0x20,current,3*sizeof(float));memcpy(record+0x30,stored,3*sizeof(float));
}

// Native 43a926d selects an all-zero actor transform for modes >= 2. Those
// modes expect presentation animation to carry world translation, whereas
// our private palette is actor-local. Only the owned mascot is detached.
inline bool mascot_use_world_position(unsigned char* record) {
    if(record[0x43]<2)return false;
    record[0x43]=0;
    record[0x45]=0; // Rebuild the cached transform; keep the animation binding.
    return true;
}
inline void mascot_restore_position_mode(unsigned char* record,unsigned char original) {
    if(record[0x43]==0&&original>=2){record[0x43]=original;record[0x45]=0;}
}
