#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef void (*GetServiceDescriptorFn)(void *);
static unsigned char *g_module_base;
static SIZE_T g_module_size;
static unsigned char manager_bytes[0x188];
static int vector_row[8], delivered, added, mock_club=1043;
static int fce_runtime_is_stable(void) { return 1; }
static int is_readable_range(const void *p,SIZE_T n) { return p && n; }
static int resolve_user_club_id(void *owner,FILE *log) { (void)owner;(void)log;return mock_club; }
static void append_loader_log(const char *text) { (void)text; }
static void *owner_service(void *owner,GetServiceDescriptorFn descriptor,int *index)
{
    (void)owner;(void)index;
    if((uintptr_t)descriptor==(uintptr_t)(g_module_base+0x04456a60)) return manager_bytes;
    return manager_bytes;
}
#include "../../src/host/career_job_offer.inc"
static void gather(void *service,int target,int seed,int *out)
{
    (void)service;(void)seed;
    memset(out,0,40);out[4]=target;out[2]=5;out[7]=5;out[9]=4;out[8]=1;
}
static void add(void *manager,const int *record,int league)
{
    int row[8]={record[4],league,record[2],record[7],record[9],record[8],-1,38000};
    (void)manager;memcpy(vector_row,row,32);
    *(uintptr_t *)(manager_bytes+0xd8)=(uintptr_t)vector_row;
    *(uintptr_t *)(manager_bytes+0xe0)=(uintptr_t)(vector_row+8);++added;
}
static void inform(void *manager,int *offer,unsigned char user_browse)
{
    (void)manager;
    assert(offer[0]==383 && offer[1]==7 && offer[2]==5);
    assert(offer[3]==5 && offer[4]==4 && offer[5]==1 && offer[7]==38000);
    assert(offer[8]==-1 && offer[9]==-1 && offer[10]==-1 && user_browse==1);
    offer[6]=20260409;++delivered;
    career_job_offer_deliver(manager_bytes); /* Reentrant callbacks cannot duplicate. */
}
static void thunk(size_t offset,uintptr_t target,int shadow_offset)
{
    unsigned char code[]={0x48,0x89,0x5c,0x24,0x08,0x48,0xb8,0,0,0,0,0,0,0,0,0xff,0xe0};
    code[4]=(unsigned char)shadow_offset;memcpy(code+7,&target,8);
    memcpy(g_module_base+offset,code,sizeof(code));
}
static void stage(void)
{
    int offer[11]={383,7,0,0,0,0,20260409,38000,1043,CAREER_JOB_OFFER_MARKER,-1};
    memcpy(manager_bytes+0x158,offer,sizeof(offer));
}
int main(void)
{
    g_module_size=0x05be0000;
    g_module_base=(unsigned char *)VirtualAlloc(NULL,g_module_size,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE);
    assert(g_module_base);
    thunk(0x05aa4120,(uintptr_t)gather,0x18);thunk(0x05b57860,(uintptr_t)add,8);thunk(0x05bcfaa0,(uintptr_t)inform,8);
    *(uintptr_t *)manager_bytes=(uintptr_t)(g_module_base+0x03071270);
    *(uintptr_t *)(manager_bytes+0x150)=(uintptr_t)(g_module_base+0x03071250);
    stage();mock_club=598;career_job_offer_deliver(manager_bytes);assert(!delivered && !added);
    mock_club=1043;g_module_base[0x05bcfaa0]=0xcc;
    career_job_offer_deliver(manager_bytes);assert(!delivered && !added);
    thunk(0x05bcfaa0,(uintptr_t)inform,8);
    career_job_offer_deliver(manager_bytes);assert(delivered==1 && added==1);
    career_job_offer_deliver(manager_bytes);assert(delivered==1 && added==1);
    stage();((int *)(manager_bytes+0x158))[9]=38000;
    career_job_offer_deliver(manager_bytes);assert(delivered==1 && added==1);
    VirtualFree(g_module_base,0,MEM_RELEASE);
    puts("PASS: guarded native delivery obtains club data, creates offer, informs once; ordinary offers untouched");
    return 0;
}

