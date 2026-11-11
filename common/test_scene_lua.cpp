#define WIN32_LEAN_AND_MEAN
#include "scene_lua.h"
#include "scene_resource_cycle.h"
#include <cassert>
#include <cstdio>
struct Value{uint64_t bits;int tag,padding;};
struct Node{Value value,key;uintptr_t next;};
struct Text{unsigned char header[16]{};size_t length=0;char value[64]{};};
int main(){
    SceneResourceCycle cycle;
    assert(!cycle.refresh(false,false));cycle.requested=true;
    cycle.complete(true,false);
    // Pending asynchronous loading is never restarted every callback.
    for(int i=0;i<120;++i)assert(!cycle.refresh(true,false));
    cycle.complete(true,true);
    assert(!cycle.refresh(true,true));
    // Captured in the Mirassol failure: same pointers, initialized=0, loaded=1.
    assert(cycle.refresh(false,true));assert(!cycle.requested);
    cycle.requested=true;cycle.complete(true,false);
    assert(!cycle.refresh(true,false));
    // A scene may also unload during its first pending request.
    assert(cycle.refresh(false,true));assert(!cycle.requested);
    cycle.requested=true;cycle.complete(true,true);
    assert(cycle.refresh(true,false));assert(!cycle.requested);

    alignas(8) unsigned char table[64]{};Node nodes[64]{};Text text;
    const char* marker="FIFA16_SMOKE_MACHINE_HOOK_READY";
    text.length=std::strlen(marker);strcpy_s(text.value,marker);
    table[8]=5;table[11]=6;const uintptr_t buckets=(uintptr_t)nodes;
    std::memcpy(table+32,&buckets,8);
    nodes[43].key={(uint64_t)(uintptr_t)&text,4,0};nodes[43].value={1,1,0};
    assert(scene_lua_flag((uintptr_t)table,marker));
    assert(!scene_lua_flag((uintptr_t)table,"absent"));
    nodes[43].value.bits=0xdeadbeef00000000ull; // Boolean false, unused union bytes dirty.
    assert(!scene_lua_flag((uintptr_t)table,marker));
    nodes[43].value={1,3,0};assert(!scene_lua_flag((uintptr_t)table,marker));
    nodes[43].value={1,1,0};table[11]=13;assert(!scene_lua_flag((uintptr_t)table,marker));
    table[11]=6;table[8]=0;assert(!scene_lua_flag((uintptr_t)table,marker));
    assert(!scene_lua_flag(0,marker));
    assert(!scene_lua_flag(1,marker));
    // Only one page of a fake image is committed, with a realistic VM pointer.
    auto fake=(unsigned char*)VirtualAlloc(nullptr,0x3615000,MEM_RESERVE,PAGE_NOACCESS);assert(fake);
    assert(VirtualAlloc(fake+0x3613000,0x2000,MEM_COMMIT,PAGE_READWRITE));
    alignas(8) unsigned char vm[0x90]{};const uintptr_t vmAddress=(uintptr_t)vm,globals=(uintptr_t)table;
    std::memcpy(fake+0x3613fd0,&vmAddress,8);std::memcpy(vm+0x78,&globals,8);
    int tag=5;std::memcpy(vm+0x80,&tag,4);
    auto snapshot=scene_lua_snapshot((uintptr_t)fake);
    assert(snapshot.vm==vmAddress&&snapshot.globals==globals);
    tag=0;std::memcpy(vm+0x80,&tag,4);snapshot=scene_lua_snapshot((uintptr_t)fake);
    assert(!snapshot.vm&&!snapshot.globals);
    assert(VirtualFree(fake,0,MEM_RELEASE));
    std::puts("Scene Lua snapshots and bounded x64 marker reader: PASS");
}
