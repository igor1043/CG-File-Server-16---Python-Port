// Exercise production callbacks against local data and the unchanged native
// transform-selection branch. No FIFA process is opened.
#include "mascot_goal_line.cpp"
#include <cassert>
int main(){
    static const unsigned char code[]={
        0x53,0x55,0x48,0x83,0xec,0x58,0x48,0x89,0xcb,0x48,0x89,0xe5,
        // Captured 43a926d..43a928f, unchanged, including both branch targets.
        0x80,0x7b,0x43,0x02,0x73,0x0e,0x0f,0x28,0x43,0x20,0x48,0x8d,0x45,0x20,
        0x0f,0x29,0x45,0x20,0xeb,0x0b,0x0f,0x57,0xc0,0x48,0x8d,0x45,0x10,
        0x0f,0x29,0x45,0x10,0x0f,0x28,0x00,
        0x0f,0x11,0x02,0x48,0x83,0xc4,0x58,0x5d,0x5b,0xc3};
    void* memory=VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);assert(memory);
    memcpy(memory,code,sizeof(code));DWORD old=0;assert(VirtualProtect(memory,4096,PAGE_EXECUTE_READ,&old));
    FlushInstructionCache(GetCurrentProcess(),memory,sizeof(code));
    auto native=(void(*)(const unsigned char*,float*))(uintptr_t)memory;
    alignas(16) unsigned char renderer[0x2000]{};
    alignas(16) unsigned char records[14][0x50]{};
    unsigned char prototypes[3][0x20]{};uintptr_t pointers[3]{};
    for(uint16_t i=0;i<3;++i){
        const uint16_t type=18;memcpy(prototypes[i]+12,&type,2);memcpy(prototypes[i]+14,&i,2);
        pointers[i]=(uintptr_t)prototypes[i];
    }
    const uintptr_t pv[3]={(uintptr_t)pointers,(uintptr_t)(pointers+3),(uintptr_t)(pointers+3)};
    const uintptr_t rv[3]={(uintptr_t)records,(uintptr_t)(records+14),(uintptr_t)(records+14)};
    memcpy(renderer+0x30*19,pv,sizeof(pv));memcpy(renderer+0x30*65,rv,sizeof(rv));
    auto* actor=records[3];actor[0x42]=2;
    *(uint16_t*)(actor+0x40)=73;mascotAnimationBound=true;
    const float goal[3]={-5850,0,3150};float out[4]{};
    mascotPlacementGeneration=11;repositionMascot=true;
    for(unsigned value:{0u,1u,2u,3u}){
        const auto mode=(unsigned char)value;
        mascot_store_position(actor,goal);actor[0x43]=mode;actor[0x45]=1;actor[0x44]=2;
        native(actor,out);
        assert(out[0]==(mode>=2?0:goal[0]));
        mascotBuildSnapshot={(uintptr_t)renderer,(uintptr_t)records,14,3,18,11,GetTickCount64(),{}};
        memcpy(mascotBuildSnapshot.position,goal,sizeof(goal));
        // Presentation runs after selection and changes the position/mode.
        const float zero[3]{};mascot_store_position(actor,zero);
        const uintptr_t token=Fifa16MascotBeforeNativeBuild(renderer);assert(token);
        native(actor,out);assert(out[0]==goal[0]&&out[1]==goal[1]&&out[2]==goal[2]);
        assert(actor[0x43]<2&&actor[0x42]==2);
        assert(actor[0x44]==0&&mascotNativeMotion.active);
        Fifa16MascotAfterNativeBuild(renderer,token);
        assert(!mascotBuildSnapshot.renderer&&sceneBusy==0);
        assert(Fifa16MascotBeforeNativeBuild(renderer)==0); // A frame is consumed once.
        mascot_restore_position_mode(actor,mode);assert(actor[0x43]==mode);
        assert(mascot_release_native_motion(actor,mascotNativeMotion)&&actor[0x44]==2);
    }
    unsigned char before[sizeof(records)];memcpy(before,records,sizeof(records));
    for(unsigned failure=0;failure<8;++failure){
        mascotBuildSnapshot={(uintptr_t)renderer,(uintptr_t)records,14,3,18,11,GetTickCount64(),{}};
        if(failure==0)mascotBuildSnapshot.renderer+=16;
        if(failure==1)mascotBuildSnapshot.records+=16;
        if(failure==2)mascotBuildSnapshot.count=13;
        if(failure==3)mascotBuildSnapshot.index=14;
        if(failure==4)mascotBuildSnapshot.generation=10;
        if(failure==5)mascotBuildSnapshot.tick-=2001;
        if(failure==6)sceneBusy=1;
        if(failure==7)repositionMascot=false;
        assert(Fifa16MascotBeforeNativeBuild(renderer)==0);
        sceneBusy=0;repositionMascot=true;
        assert(!memcmp(before,records,sizeof(records)));
    }
    for(size_t i=0;i<14;++i)if(i!=3)for(unsigned char byte:records[i])assert(byte==0);
    assert(VirtualFree(memory,0,MEM_RELEASE));
    puts("PASS exact native origin branch and production bridge: modes 2/3 ignore correct coordinates before fix; all modes use target after fix; post-selection transition repaired; original mode restored; stale/foreign/contended frames and other actors untouched");
}
