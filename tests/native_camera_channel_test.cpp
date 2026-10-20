#define WIN32_LEAN_AND_MEAN
#define SERVER16_CAMERA_TEST
#include <windows.h>
#include <cassert>
#include <cstdio>
#include "../native_mods/first_person/camera_channel.h"
int main(){
    // Use the actual worker in a non-FIFA process: unsupported activation must
    // fail before it ever reaches a game's camera slots.
    HANDLE mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(CameraChannel),CAMERA_MAPPING_NAME);assert(mapping);
    assert(GetLastError()!=ERROR_ALREADY_EXISTS); // Never touch a running Server.
    auto* s=static_cast<CameraChannel*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(CameraChannel)));assert(s);
    s->version=4;s->owner=GetCurrentProcessId();s->heartbeat=GetTickCount();s->command=1;s->profile=2;s->framing=1;s->fov=105;
    HMODULE dll=LoadLibraryW(L"build\\server16_first_person_test.dll");assert(dll);
    auto wait=[&](uint32_t command){for(int i=0;i<100&&s->ack!=command;++i){s->heartbeat=GetTickCount();Sleep(10);}assert(s->ack==command);};
    wait(1);assert(s->ready==1&&s->enabled==0&&s->error==0);
    s->profile=7;s->command=2;wait(2);assert(s->error==2&&s->enabled==0);
    s->profile=1;s->requested=1;s->command=3;wait(3);assert(s->error==1&&s->enabled==0);
    s->requested=0;s->command=4;wait(4);assert(s->error==0&&s->enabled==0);
    s->fov=151;s->command=5;wait(5);assert(s->error==2&&s->enabled==0);
    s->fov=105;s->look_bias=-11;s->command=6;wait(6);assert(s->error==2);
    s->look_bias=8;s->command=7;wait(7);assert(s->error==0);
    s->mode=2;s->command=8;wait(8);assert(s->error==2);
    s->mode=1;s->fov=75;s->command=9;wait(9);assert(s->error==0&&s->enabled==0);
    s->fov=105;s->command=10;wait(10);assert(s->error==2);
    s->fov=60;s->command=11;wait(11);assert(s->error==0);
    s->mode=0;s->command=12;wait(12);assert(s->error==2);
    s->mode=1;s->distance=3;s->command=13;wait(13);assert(s->error==2);
    s->distance=2;s->command=14;wait(14);assert(s->error==0);
    s->mode=0;s->fov=150;s->command=15;wait(15);assert(s->error==0&&s->enabled==0);
    s->mode=1;s->command=16;wait(16);assert(s->error==2&&s->enabled==0);
    s->mode=0;s->fov=151;s->command=17;wait(17);assert(s->error==2&&s->enabled==0);
    s->fov=150;s->profile=3;s->command=18;wait(18);assert(s->error==0);
    s->profile=4;s->command=19;wait(19);assert(s->error==2);
    s->owner=0;Sleep(80);assert(s->enabled==0);
    std::puts("PASS: real DLL channel, ack, FOV/tilt/mode bounds, unsupported executable rejection, disable and owner loss");
    // Exit ends the worker; do not unload while its thread is running.
    return 0;
}
