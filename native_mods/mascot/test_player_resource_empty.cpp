#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <cassert>
static uintptr_t image=0;
template<class T>static bool get(uintptr_t at,T& out){SIZE_T count=0;return ReadProcessMemory(GetCurrentProcess(),(void*)at,&out,sizeof out,&count)&&count==sizeof out;}
static bool readable(uintptr_t at,size_t n){MEMORY_BASIC_INFORMATION m{};return VirtualQuery((void*)at,&m,sizeof m)&&m.State==MEM_COMMIT&&!(m.Protect&(PAGE_NOACCESS|PAGE_GUARD))&&at+n<=(uintptr_t)m.BaseAddress+m.RegionSize;}
static void log_event(const char*,...){}
#include "player_resource_recovery.h"
int main(){
    alignas(16) unsigned char composite[24]{},resource[128]{},assets[3*72]{};
    const uintptr_t r=(uintptr_t)resource,a=(uintptr_t)assets,e=a+sizeof assets;
    memcpy(composite,&r,8);memcpy(resource+0x58,&a,8);memcpy(resource+0x60,&e,8);
    assert(player_resource_empty((uintptr_t)composite));
    composite[16]=1;assert(!player_resource_empty((uintptr_t)composite));composite[16]=0;
    resource[0x50]=1;assert(!player_resource_empty((uintptr_t)composite));resource[0x50]=0;
    resource[0x51]=1;assert(!player_resource_empty((uintptr_t)composite));resource[0x51]=0;
    const uintptr_t pending=123;memcpy(assets+72+40,&pending,8);
    assert(!player_resource_empty((uintptr_t)composite));memset(assets,0,sizeof assets);
    uintptr_t wrong=e-1;memcpy(resource+0x60,&wrong,8);assert(!player_resource_empty((uintptr_t)composite));
    wrong=a+72*129;memcpy(resource+0x60,&wrong,8);assert(!player_resource_empty((uintptr_t)composite));
    assert(!player_resource_empty(0));
    recover_player_resources(1000); // No native world -> no prepare/call.
}
