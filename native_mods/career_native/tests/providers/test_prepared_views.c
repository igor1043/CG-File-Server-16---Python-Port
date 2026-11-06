#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef struct CareerContextRead {DWORD schema,size;LONG sequence;DWORD pid;uintptr_t service,vtable,registry;DWORD epoch,owner_thread;} CareerContextRead;
typedef struct FceFixture {int played_raw,date_raw,home,away,time_raw,id;} FceFixture;
typedef struct FceModel {FceFixture *fixtures;size_t fixture_count;} FceModel;
typedef struct FceLiveSnapshot {FceModel model;} FceLiveSnapshot;
static CareerContextRead Fifa16CareerContextRead;
static FceFixture fixture={0,20260112,1043,517,1600,88};static FceLiveSnapshot mock_snapshot={{&fixture,1}};
static unsigned char *g_module_base,*mock_calendar;static char g_mod_dir[MAX_PATH],mock_page[128];
static void *g_current_stats_provider_owner;static int stable=1,calls,ack;static DWORD owner_thread;
static uintptr_t mock_manager[4],mock_bus[2],mock_allocator[1],mock_allocator_vtable[3];
static int allocation_failure,constructed,released;static char queued_event[80];
static int fce_runtime_is_stable(void){return stable;}
static unsigned long fce_runtime_context_epoch(void){return 2;}
static FceLiveSnapshot *fce_runtime_cached_acquire(void){return &mock_snapshot;}
static const FceModel *fce_runtime_model(FceLiveSnapshot *value){return &value->model;}
static void fce_runtime_release(FceLiveSnapshot *value){(void)value;}
static int fce_date_pack(int day,int month,int year){return year*10000+month*100+day;}
static int is_readable_range(const void *p,size_t n){MEMORY_BASIC_INFORMATION m;return p && VirtualQuery(p,&m,sizeof(m)) && m.State==MEM_COMMIT && !(m.Protect&(PAGE_NOACCESS|PAGE_GUARD)) && (uintptr_t)p+n<=(uintptr_t)m.BaseAddress+m.RegionSize;}
static int read_card_scope(uintptr_t p,void *out,size_t n){if(!is_readable_range((void *)p,n))return 0;memcpy(out,(void *)p,n);return 1;}
static unsigned char *bank_mail_service(uintptr_t registry,unsigned descriptor,size_t n){
    (void)registry;(void)n;
    return descriptor==0x4456990?(unsigned char *)mock_manager:
        descriptor==0x44568e0?(unsigned char *)mock_bus:mock_calendar;
}
static void append_loader_log(const char *event){(void)event;}
static int bank_input_context(CareerContextRead *out,uintptr_t *context,unsigned *club,int *date){
    *out=Fifa16CareerContextRead;*context=*(uintptr_t *)(out->service+0x18);*club=1043;*date=20260111;return 1;
}
#include "../../src/host/career_prepared_views.inc"
static void *allocate(void *allocator,unsigned size,const char *name,unsigned flags){
    assert(allocator==mock_allocator && size==0x98 && name==(const char *)(g_module_base+0x3055600) && !flags);
    return allocation_failure?NULL:calloc(1,size);
}
static void *construct(void *memory,const char *event){
    assert(GetCurrentThreadId()==owner_thread);strcpy((char *)memory+0x18,event);++constructed;return memory;
}
static void submit(void *bus,void *message){
    assert(bus==mock_bus && GetCurrentThreadId()==owner_thread);++calls;
    strcpy(queued_event,(char *)message+0x18);free(message);++released;
}
static void process_queued(void){
    if(ack && queued_event[0]){
        strcpy(mock_page,!strcmp(queued_event,"Back")?"game/screens/fluxHub/FluxHub":strstr(queued_event,"Manager")?"game/screens/career/server16/ManagerMarket":strstr(queued_event,"Finance")?"game/screens/career/server16/ClubFinance":strstr(queued_event,"Dressing")?"game/screens/career/server16/DressingRoom":strstr(queued_event,"Transfer")?"game/screens/career/server16/TransferMarket":"game/screens/career/server16/MatchPreview");queued_event[0]=0;
    }
}
static void trampoline(unsigned offset,uintptr_t callback,int prefix){
    unsigned char code[19]={0x48,0x89,0x74,0x24,0x10,0xff,0x25,0,0,0,0};
    if(prefix){memcpy(code+11,&callback,8);memcpy(g_module_base+offset,code,19);}
    else{memcpy(code,"\xff\x25\0\0\0\0",6);memcpy(code+6,&callback,8);memcpy(g_module_base+offset,code,14);}
}
static void write_ready(const char *file,const PreparedViewRecord *r){
    FILE *f=fopen(file,"wb");assert(f);
    fprintf(f,"schema=%u\npid=%u\nclub=%u\nepoch=%u\nprocess_created_100ns=%llu\ncontext=%llx\nregistry=%llx\ncaptured_ms=%llu\ndate=%d\nfixture=%d\nrevision=%s\n",r->schema,r->pid,r->club,r->epoch,r->created,r->context,r->registry,r->captured,r->date,r->fixture,r->revision);assert(!fclose(f));
}
static void tick(void){int i;for(i=0;i<5;++i)g_prepared_views[i].next=0;drain_prepared_views();process_queued();}
int main(void){
    unsigned char service[32]={0},contexts[0x318]={0},cal[80]={0};uintptr_t nodes[4][64]={{0}},vtable[2]={0};
    char temp[MAX_PATH],folder[MAX_PATH],preview[MAX_PATH],market[MAX_PATH];FILETIME created,exit,kernel,user;ULARGE_INTEGER identity;
    PreparedViewRecord good={0},bad;int before,i;uintptr_t allocator_address=(uintptr_t)mock_allocator;
    owner_thread=GetCurrentThreadId();assert(GetTempPathA(sizeof(temp),temp));assert(GetTempFileNameA(temp,"pvw",0,g_mod_dir));DeleteFileA(g_mod_dir);assert(CreateDirectoryA(g_mod_dir,NULL));
    snprintf(folder,sizeof(folder),"%s\\runtime",g_mod_dir);assert(CreateDirectoryA(folder,NULL));strcat(folder,"\\club_environment");assert(CreateDirectoryA(folder,NULL));
    snprintf(preview,sizeof(preview),"%s\\preview",folder);assert(CreateDirectoryA(preview,NULL));strcat(preview,"\\runtime");assert(CreateDirectoryA(preview,NULL));strcat(preview,"\\view_ready.tsv");
    snprintf(market,sizeof(market),"%s\\market",folder);assert(CreateDirectoryA(market,NULL));strcat(market,"\\view_ready.tsv");
    g_module_base=VirtualAlloc(NULL,0x6000000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);assert(g_module_base);
    *(uintptr_t *)(g_module_base+0x3809030)=(uintptr_t)nodes[0];nodes[0][232/8]=(uintptr_t)nodes[1];nodes[1][192/8]=(uintptr_t)nodes[2];nodes[2][136/8]=(uintptr_t)nodes[3];nodes[3][472/8]=(uintptr_t)mock_page;
    *(uintptr_t *)service=(uintptr_t)vtable;*(uintptr_t *)(service+0x18)=(uintptr_t)contexts;*(int *)(contexts+0x18c)=1;*(int *)(contexts+0x1a4)=1043;
    mock_calendar=cal;((int *)(cal+0x34))[0]=11;((int *)(cal+0x34))[1]=1;((int *)(cal+0x34))[2]=2026;
    Fifa16CareerContextRead=(CareerContextRead){1,sizeof(CareerContextRead),2,GetCurrentProcessId(),(uintptr_t)service,(uintptr_t)vtable,123,2,owner_thread};
    mock_manager[0]=(uintptr_t)g_module_base+0x21b5720;mock_manager[3]=456;
    *(uintptr_t *)(g_module_base+0x21b5720+0x40)=(uintptr_t)g_module_base+0x49fbe20;
    mock_bus[0]=(uintptr_t)g_module_base+0x21b5530;
    *(uintptr_t *)(g_module_base+0x21b5530+0x10)=(uintptr_t)g_module_base+0x4042000;
    mock_allocator[0]=(uintptr_t)mock_allocator_vtable;mock_allocator_vtable[2]=(uintptr_t)allocate;
    memcpy(g_module_base+0x4467990,"\x48\x8b\x05\x01\0\0\0\xc3",8);memcpy(g_module_base+0x4467998,&allocator_address,8);
    trampoline(0x5c56b40,(uintptr_t)construct,1);trampoline(0x4042000,(uintptr_t)submit,0);
    FlushInstructionCache(GetCurrentProcess(),g_module_base,0x6000000);
    assert(GetProcessTimes(GetCurrentProcess(),&created,&exit,&kernel,&user));identity.LowPart=created.dwLowDateTime;identity.HighPart=created.dwHighDateTime;
    good=(PreparedViewRecord){1,GetCurrentProcessId(),1043,2,identity.QuadPart,(uintptr_t)contexts,123,GetTickCount64(),20260111,88,{0}};memset(good.revision,'a',64);
    strcpy(mock_page,"game/screens/career/server16/MatchPreviewLoading");tick();assert(!calls);good.captured=GetTickCount64();write_ready(preview,&good);
    tick();assert(calls==1);tick();assert(calls==2); /* A busy controller may ignore a load; waiting retries. */
    ack=1;tick();assert(calls==3);tick();assert(calls==3); /* Ready data must never reload in a loop. */
    before=calls;strcpy(mock_page,"game/screens/career/server16/MatchPreviewLoading");
    for(i=0;i<10;++i){bad=good;bad.captured=GetTickCount64();
        switch(i){case 0:++bad.pid;break;case 1:++bad.created;break;case 2:++bad.context;break;case 3:++bad.registry;break;case 4:++bad.epoch;break;case 5:++bad.club;break;case 6:++bad.date;break;case 7:++bad.fixture;break;case 8:bad.captured=GetTickCount64()+100000;break;default:bad.captured=GetTickCount64()-13000;break;}
        write_ready(preview,&bad);tick();assert(calls==before);
    }
    good.captured=GetTickCount64();write_ready(preview,&good);++Fifa16CareerContextRead.owner_thread;tick();assert(calls==before);--Fifa16CareerContextRead.owner_thread;
    ++mock_bus[0];tick();assert(calls==before);--mock_bus[0];
    ++mock_manager[0];tick();assert(calls==before);--mock_manager[0];
    allocation_failure=1;tick();assert(calls==before);allocation_failure=0;
    stable=0;tick();assert(calls==before);stable=1;g_current_stats_provider_owner=(void *)1;tick();assert(calls==before);g_current_stats_provider_owner=NULL;
    g_prepared_views[0].entered=good.captured+1;tick();assert(calls==before);g_prepared_views[0].entered=0;tick();assert(calls==before+1);
    strcpy(mock_page,"game/screens/career/server16/TransferMarketLoading");tick();assert(calls==before+1);good.captured=GetTickCount64();good.fixture=0;write_ready(market,&good);tick();assert(calls==before+2);tick();assert(calls==before+2);
    {char room[MAX_PATH];
     snprintf(room,sizeof(room),"%s\\room",folder);assert(CreateDirectoryA(room,NULL));strcat(room,"\\runtime");assert(CreateDirectoryA(room,NULL));strcat(room,"\\view_ready.tsv");
     strcpy(mock_page,"game/screens/career/server16/DressingRoom");good.captured=GetTickCount64();memset(good.revision,'c',64);write_ready(room,&good);
     before=calls;tick();assert(calls==before+1 && !strcmp(queued_event,""));tick();assert(calls==before+1);
     /* The same prepared screen does not reload after every re-entry. */
     strcpy(mock_page,"game/screens/fluxHub/FluxHub");tick();strcpy(mock_page,"game/screens/career/server16/DressingRoom");tick();assert(calls==before+1);
     DeleteFileA(room);*strrchr(room,'\\')=0;assert(RemoveDirectoryA(room));*strrchr(room,'\\')=0;assert(RemoveDirectoryA(room));
    }
    {char finance[MAX_PATH];
     snprintf(finance,sizeof(finance),"%s\\bank",folder);assert(CreateDirectoryA(finance,NULL));strcat(finance,"\\runtime");assert(CreateDirectoryA(finance,NULL));strcat(finance,"\\view_ready.tsv");
     strcpy(mock_page,"game/screens/career/server16/ClubFinance");good.captured=GetTickCount64();memset(good.revision,'d',64);write_ready(finance,&good);
     before=calls;tick();assert(calls==before+1);tick();assert(calls==before+1);
     /* A confirmed settings revision reloads automatically, once. */
     memset(good.revision,'e',64);good.captured=GetTickCount64();write_ready(finance,&good);tick();assert(calls==before+2);tick();assert(calls==before+2);
     bad=good;++bad.club;memset(bad.revision,'f',64);write_ready(finance,&bad);tick();assert(calls==before+2);
     DeleteFileA(finance);*strrchr(finance,'\\')=0;assert(RemoveDirectoryA(finance));*strrchr(finance,'\\')=0;assert(RemoveDirectoryA(finance));
    }
    {char managers[MAX_PATH];
     snprintf(managers,sizeof(managers),"%s\\runtime\\manager_market",g_mod_dir);assert(CreateDirectoryA(managers,NULL));strcat(managers,"\\view_ready.tsv");
     strcpy(mock_page,"game/screens/career/server16/ManagerMarket");before=calls;tick();assert(calls==before);
     good.captured=GetTickCount64();memset(good.revision,'1',64);write_ready(managers,&good);tick();assert(calls==before+1);tick();assert(calls==before+1);
     /* The first placeholder refreshes automatically when the helper publishes.
        Heartbeats do not repeatedly rebuild an already-open ready screen. */
     good.captured=GetTickCount64();write_ready(managers,&good);tick();assert(calls==before+1);
     bad=good;++bad.club;memset(bad.revision,'2',64);write_ready(managers,&bad);tick();assert(calls==before+1);
     good.captured=GetTickCount64();memset(good.revision,'3',64);write_ready(managers,&good);tick();assert(calls==before+2);
     strcpy(mock_page,"game/screens/fluxHub/FluxHub");tick();strcpy(mock_page,"game/screens/career/server16/ManagerMarket");tick();assert(calls==before+2);
     DeleteFileA(managers);*strrchr(managers,'\\')=0;assert(RemoveDirectoryA(managers));
    }
    strcpy(mock_page,"game/screens/career/server16/CareerCompetitions");before=calls;
    competition_back_request();++Fifa16CareerContextRead.owner_thread;tick();assert(calls==before);--Fifa16CareerContextRead.owner_thread;
    stable=0;tick();assert(calls==before);stable=1;g_current_stats_provider_owner=(void *)1;tick();assert(calls==before);g_current_stats_provider_owner=NULL;
    tick();assert(calls==before+1&&!strcmp(mock_page,"game/screens/fluxHub/FluxHub"));tick();assert(calls==before+1);
    strcpy(mock_page,"game/screens/career/server16/CareerCompetitions");competition_back_request();++g_competition_back_context.epoch;tick();assert(calls==before+1&&!g_competition_back_until);
    competition_back_request();strcpy(mock_page,"game/screens/fluxHub/FluxHub");tick();assert(calls==before+1&&!g_competition_back_until);
    assert(constructed==released && released==calls);
    DeleteFileA(preview);DeleteFileA(market);*strrchr(preview,'\\')=0;assert(RemoveDirectoryA(preview));*strrchr(preview,'\\')=0;assert(RemoveDirectoryA(preview));*strrchr(market,'\\')=0;assert(RemoveDirectoryA(market));assert(RemoveDirectoryA(folder));*strrchr(folder,'\\')=0;assert(RemoveDirectoryA(folder));assert(RemoveDirectoryA(g_mod_dir));VirtualFree(g_module_base,0,MEM_RELEASE);
    puts("PASS prepared views: fresh current career only, skipped days/club/session rejected, owner thread, provider guard, waiting retries, no ready reload loop, both screens");return 0;
}
