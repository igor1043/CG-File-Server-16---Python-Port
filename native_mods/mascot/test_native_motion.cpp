#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cassert>
#include <cstdio>
#include "mascot_record_position.h"

int main() {
    // Same mode/locomotion gates as 43af5f9..43af603, followed by the yaw
    // writes at 43af586 / 43af645. Execute locally; never open the game.
    const unsigned char code[]={
        0x80,0x79,0x43,0x00,0x75,0x10,
        0x80,0x79,0x44,0x00,0x74,0x0a,
        0xf3,0x0f,0x11,0x49,0x1c,
        0xf3,0x0f,0x11,0x49,0x2c,0xc3};
    void* memory=VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);assert(memory);
    memcpy(memory,code,sizeof(code));DWORD protection=0;
    assert(VirtualProtect(memory,4096,PAGE_EXECUTE_READ,&protection));
    FlushInstructionCache(GetCurrentProcess(),memory,sizeof(code));
    const auto native=(void(*)(unsigned char*,float))memory;
    for(unsigned int flag:{0u,1u,2u,255u})for(float nativeYaw:{-3.14f,-1.57f,1.57f,3.14f}) {
        unsigned char record[0x50]{},other[0x50]{};
        record[0x44]=(unsigned char)flag;record[0x45]=7;other[0x44]=2;
        native(record,nativeYaw);
        float yaw=0;memcpy(&yaw,record+0x2c,sizeof(yaw));
        assert(yaw==(flag?nativeYaw:0)); // Reproduce the unwanted second rotation.
        MascotNativeMotionOwnership ownership;
        assert(mascot_control_native_motion(record,ownership));
        assert(ownership.locomotion==flag && ownership.active);
        native(record,nativeYaw);
        memcpy(&yaw,record+0x2c,sizeof(yaw));assert(yaw==0 && record[0x44]==0 && record[0x45]==7);
        assert(mascot_control_native_motion(record,ownership)); // Never save the overridden zero as the original.
        assert(!mascot_control_native_motion(other,ownership) && other[0x44]==2);
        assert(!mascot_release_native_motion(other,ownership) && ownership.active);
        assert(mascot_release_native_motion(record,ownership));
        assert(record[0x44]==flag && !ownership.active && record[0x45]==7);
        native(record,nativeYaw);memcpy(&yaw,record+0x2c,sizeof(yaw));assert(yaw==(flag?nativeYaw:0));
        assert(!mascot_release_native_motion(record,ownership));
        assert(!mascot_control_native_motion(nullptr,ownership));
    }
    assert(VirtualFree(memory,0,MEM_RELEASE));
    puts("PASS native yaw overwrite reproduced and blocked for owned mascot only; native locomotion restored on release; repeated frames and other actors preserved");
}
