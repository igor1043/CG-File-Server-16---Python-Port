#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <assert.h>
#include <string.h>
#include "../../src/core/fce_model.h"
static unsigned char *g_module_base;
static unsigned long epoch=2;
static unsigned long fce_runtime_context_epoch(void){return epoch;}
static int is_readable_range(const void *p,size_t n) {
    unsigned char b[128];SIZE_T got;
    return n<=sizeof(b) && ReadProcessMemory(GetCurrentProcess(),p,b,n,&got) && got==n;
}
#include "../../src/host/career_context_read.inc"
int main(void) {
    unsigned char registry[256*32+32]={0},service[32]={0},calendar[0x40]={0},owner[16]={0};
    uintptr_t wrapper=(uintptr_t)calendar;unsigned index=32;int parts[]={10,8,2026};
    g_module_base=VirtualAlloc(NULL,0x4456500,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);assert(g_module_base);
    memcpy(g_module_base+0x44563f0+7,"\xc7\x01",2);memcpy(g_module_base+0x44563f0+9,&index,4);
    *(uintptr_t *)(registry+index*32+24)=(uintptr_t)&wrapper;*(uintptr_t *)service=0x1234;*(uintptr_t *)(owner+8)=(uintptr_t)registry;
    memcpy(calendar+0x34,parts,sizeof(parts));publish_career_context_read(service,owner);
    assert(career_context_calendar_date()==20260810);
    parts[0]=11;memcpy(calendar+0x34,parts,sizeof(parts));assert(career_context_calendar_date()==20260811);
    parts[1]=-1;memcpy(calendar+0x34,parts,sizeof(parts));assert(career_context_calendar_date()==-1);
    ++epoch;assert(career_context_calendar_date()==-1);parts[1]=8;memcpy(calendar+0x34,parts,sizeof(parts));publish_career_context_read(service,owner);
    assert(career_context_calendar_date()==20260811);++Fifa16CareerContextRead.sequence;assert(career_context_calendar_date()==-1);
    VirtualFree(g_module_base,0,MEM_RELEASE);return 0;
}
