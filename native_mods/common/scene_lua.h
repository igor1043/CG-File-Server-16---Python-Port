#pragma once
#include <windows.h>
#include <cstdint>
#include <cstring>

// Sample on the native scene callback, never from the startup worker. A valid
// VM alone does not prove that its scripts or a replacement globals table ran.
struct SceneLuaSnapshot {
    uintptr_t vm=0,globals=0;
};
struct SceneLuaLifecycle {
    SceneLuaSnapshot current{};
    bool ready=false;
    uint64_t nextCheck=0,nextAttempt=0;
    bool sample(uint64_t now,SceneLuaSnapshot value){
        if(now<nextCheck)return false;
        nextCheck=now+500;
        if(current.vm!=value.vm||current.globals!=value.globals){
            current=value;ready=false;nextAttempt=0;
        }
        return true;
    }
    bool should_activate(uint64_t now,bool markers){
        ready=markers;
        if(!current.vm||!current.globals||ready||now<nextAttempt)return false;
        nextAttempt=now+1000;return true;
    }
};
template<class T> inline bool scene_lua_read(uintptr_t address,T& out){
    SIZE_T read=0;
    return address&&ReadProcessMemory(GetCurrentProcess(),(void*)address,&out,sizeof(out),&read)&&read==sizeof(out);
}
inline SceneLuaSnapshot scene_lua_snapshot(uintptr_t image){
    SceneLuaSnapshot result{};int tag=0;
    if(!scene_lua_read(image+0x3613fd0,result.vm)||!result.vm||
       !scene_lua_read(result.vm+0x80,tag)||tag!=5||
       !scene_lua_read(result.vm+0x78,result.globals)||!result.globals)return {};
    return result;
}
inline bool scene_lua_flag(uintptr_t table,const char* key){
    struct Value{uint64_t bits;int tag,padding;};
    struct Node{Value value,key;uintptr_t next;};
    static_assert(sizeof(Node)==40,"Lua 5.1 x64 node layout");
    unsigned char tag=0,power=0;uintptr_t nodes=0;
    if(!scene_lua_read(table+8,tag)||tag!=5||!scene_lua_read(table+11,power)||power>12||
       !scene_lua_read(table+32,nodes)||!nodes)return false;
    const size_t length=std::strlen(key);if(length>=64)return false;
    // Read buckets in small blocks rather than a system call per empty node.
    for(unsigned start=0;start<(1u<<power);start+=32){
        Node block[32]{};const unsigned remaining=(1u<<power)-start;
        const unsigned count=remaining<32?remaining:32;SIZE_T read=0;
        if(!ReadProcessMemory(GetCurrentProcess(),(void*)(nodes+start*sizeof(Node)),block,count*sizeof(Node),&read)||read!=count*sizeof(Node))return false;
        for(unsigned i=0;i<count;++i){
            const auto& node=block[i];size_t textLength=0;char text[64]{};
            if(node.key.tag!=4||!scene_lua_read((uintptr_t)node.key.bits+16,textLength)||textLength!=length)continue;
            if(ReadProcessMemory(GetCurrentProcess(),(void*)((uintptr_t)node.key.bits+24),text,length,&read)&&read==length&&
               !std::memcmp(text,key,length))return node.value.tag==1&&(node.value.bits&0xffffffffu)!=0;
        }
    }
    return false;
}
