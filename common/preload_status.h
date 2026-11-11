#pragma once
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <cstdio>

enum class ScenePreloadState : LONG { Waiting=1, Loading=2, Ready=3, Skipped=4, Failed=5 };
struct ScenePreloadRow { volatile LONG sequence,state; DWORD heartbeat,generation; };
struct ScenePreloadShared { volatile LONG version; DWORD process; ScenePreloadRow rows[4]; };
static_assert(sizeof(ScenePreloadShared)==72,"Server16 preload channel ABI");

// Each DLL owns one row. The channel is telemetry only; the Server cannot
// enable rendering, submit particles or mutate native resources through it.
inline void scene_preload_publish(unsigned module,ScenePreloadState state){
    static HANDLE mapping=nullptr;
    static ScenePreloadShared* shared=nullptr;
    static DWORD next=0;
    static LONG previous=0;
    if(module>=4)return;
    const DWORD now=GetTickCount();
    if(previous==(LONG)state&&(LONG)(now-next)<0)return;
    if(!shared){
        wchar_t name[80]{};swprintf_s(name,L"Local\\FIFA16_PresentationLoad_v1_%lu",GetCurrentProcessId());
        mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(ScenePreloadShared),name);
        if(!mapping)return;
        const bool fresh=GetLastError()!=ERROR_ALREADY_EXISTS;
        shared=(ScenePreloadShared*)MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(ScenePreloadShared));
        if(!shared){CloseHandle(mapping);mapping=nullptr;return;}
        if(fresh){shared->process=GetCurrentProcessId();MemoryBarrier();InterlockedExchange(&shared->version,1);}
    }
    if(shared->version!=1||shared->process!=GetCurrentProcessId())return;
    auto& row=shared->rows[module];
    InterlockedIncrement(&row.sequence);
    if(previous!=(LONG)state)++row.generation;
    row.state=(LONG)state;row.heartbeat=now;
    MemoryBarrier();InterlockedIncrement(&row.sequence);
    previous=(LONG)state;next=now+500;
}

inline bool scene_preload_preview(const char* text){
    if(!text)return false;
    char page[192]{};size_t n=0;
    for(;text[n]&&n+1<sizeof(page);++n){const char c=text[n];page[n]=(c>='A'&&c<='Z')?(char)(c+32):c;}
    if(text[n])return false;
    return !strcmp(page,"game/screens/playnow/kickoffhub")||strstr(page,"kitselect")||
        strstr(page,"kit_select")||strstr(page,"selectkit")||strstr(page,"prematchhub");
}

inline bool scene_preload_context(const char* game,bool preview,uintptr_t& fixture,unsigned& competition,unsigned& round){
    fixture=0;competition=round=0;if(!preview)return false;
    char path[MAX_PATH]{};WIN32_FILE_ATTRIBUTE_DATA file{};FILETIME created{},exited{},kernel{},user{};
    if(_snprintf_s(path,MAX_PATH,_TRUNCATE,"%s\\runtime\\entrance_props_context.ini",game)<0||
       !GetFileAttributesExA(path,GetFileExInfoStandard,&file)||
       !GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user)||
       CompareFileTime(&file.ftLastWriteTime,&created)<0||
       GetPrivateProfileIntA("selection","schema",0,path)!=1||
       GetPrivateProfileIntA("selection","process_id",0,path)!=GetCurrentProcessId()||
       GetPrivateProfileIntA("selection","preview",0,path)!=1)return false;
    const unsigned home=GetPrivateProfileIntA("selection","home",0,path),away=GetPrivateProfileIntA("selection","away",0,path);
    competition=GetPrivateProfileIntA("selection","competition",0,path);round=GetPrivateProfileIntA("selection","round",0,path);
    if(!home||home>=1000000||!away||away>=1000000||competition>=1000000||round>=1000000)return false;
    fixture=((uintptr_t)home<<32)|away;return true;
}
