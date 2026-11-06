#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef struct CareerContextRead {DWORD schema,size;LONG sequence;DWORD pid;uintptr_t service,vtable,registry;DWORD epoch,owner_thread;} CareerContextRead;
typedef struct NativeNameDbApi {
    void *(*query_init)(void *,int,const char *);void (*where_int)(void *,const char *,int,int);
    void *(*result_init)(void *);int (*count)(void *);int (*integer)(void *,int,const char *);
    const char *(*string)(void *,int,const char *);void (*result_free)(void *);void (*query_free)(void *);
} NativeNameDbApi;
static NativeNameDbApi native_name_db;
static CareerContextRead Fifa16CareerContextRead;
static unsigned char *g_module_base,*mock_calendar,*name_service;
static void *g_current_stats_provider_owner;
static char g_mod_dir[MAX_PATH];
static int stable=1,queries,mode;
static int fce_runtime_is_stable(void){return stable;}
static unsigned long fce_runtime_context_epoch(void){return 2;}
static int fce_date_valid(int n){return n==20260111;}
static int is_readable_range(const void *p,size_t n){MEMORY_BASIC_INFORMATION m;return p && VirtualQuery(p,&m,sizeof(m)) && m.State==MEM_COMMIT && !(m.Protect&(PAGE_NOACCESS|PAGE_GUARD)) && (uintptr_t)p+n<=(uintptr_t)m.BaseAddress+m.RegionSize;}
static int read_card_scope(uintptr_t p,void *out,size_t n){if(!is_readable_range((void *)p,n))return 0;memcpy(out,(void *)p,n);return 1;}
static unsigned char *bank_mail_service(uintptr_t registry,unsigned descriptor,size_t n){(void)registry;(void)n;return descriptor==0x44563f0?mock_calendar:name_service;}
#include "../../src/host/career_market_read.inc"
typedef struct PreparedViewRecord {unsigned schema,pid,club,epoch;unsigned long long created,context,registry,captured;int date,fixture;char revision[65];} PreparedViewRecord;
static PreparedViewRecord manager_request;
static int manager_request_enabled;
static int prepared_view_read_file(const char *path,PreparedViewRecord *record){(void)path;*record=manager_request;return manager_request_enabled;}
static int prepared_view_scope(const PreparedViewRecord *record,CareerContextRead *captured){
    *captured=Fifa16CareerContextRead;
    return captured->sequence==2 && captured->owner_thread==GetCurrentThreadId()
        && record->pid==GetCurrentProcessId() && record->date==20260100+((int *)(mock_calendar+0x34))[0] && record->club==1043
        && record->epoch==captured->epoch && record->registry==captured->registry;
}
static int bank_input_context(CareerContextRead *captured,uintptr_t *context,unsigned *club,int *today){
    *captured=Fifa16CareerContextRead;*context=(uintptr_t)*(void **)(captured->service+0x18);
    *club=1043;*today=20260100+((int *)(mock_calendar+0x34))[0];return 1;
}
static int campaign_archives;
#define MANAGER_ARCHIVE_CAMPAIGN(r) ((void)(r),++campaign_archives)
#include "../../src/host/career_manager_read.inc"
typedef struct Query {const char *table;int value;} Query;
static void *q_init(void *q,int operation,const char *table){assert(operation==1);memset(q,0,56);((Query *)q)->table=table;++queries;return q;}
static void q_where(void *q,const char *field,int op,int value){(void)field;assert(op==0);((Query *)q)->value=value;}
static void *r_init(void *r){*(void **)r=NULL;return r;}
static void execute(void *backend,void *q,void *r){(void)backend;*(void **)r=q;if(mode==2)++Fifa16CareerContextRead.sequence;}
static int r_count(void *r){Query *q=*(Query **)r;if(mode==1)return MARKET_READ_MAX+1;return strcmp(q->table,"career_precontract")?1:0;}
static int r_int(void *r,int row,const char *field){Query *q=*(Query **)r;(void)row;
    if(!strcmp(field,"offerid"))return 12;if(!strcmp(field,"result"))return 32;
    if(!strcmp(field,"playerid"))return 234;if(!strcmp(field,"date"))return 20260110;
    if(!strcmp(field,"offeredfee"))return 7000000;if(!strcmp(field,"teamid"))return !strcmp(q->table,"teamplayerlinks")?1043:1;
    if(!strcmp(field,"offerteamid"))return 1043;if(!strcmp(field,"overallrating"))return 82;
    if(!strcmp(field,"potential"))return 86;return 0;}
static void release(void *p){(void)p;}
int main(void){
    unsigned char career[32]={0},contexts[0x318]={0},cal[64]={0};
    uintptr_t nodes[4][64]={{0}},backend[2],vtable[2],names[1];
    char page[96]="game/screens/career/server16/TransferMarket",temp[MAX_PATH],file[MAX_PATH],buffer[8192];FILE *f;size_t n;
    assert(GetTempPathA(sizeof(temp),temp));assert(GetTempFileNameA(temp,"mkt",0,g_mod_dir));DeleteFileA(g_mod_dir);assert(CreateDirectoryA(g_mod_dir,NULL));
    snprintf(file,sizeof(file),"%s\\runtime",g_mod_dir);assert(CreateDirectoryA(file,NULL));strcat(file,"\\club_environment");assert(CreateDirectoryA(file,NULL));strcat(file,"\\market");assert(CreateDirectoryA(file,NULL));strcat(file,"\\live_market.tsv");
    g_module_base=VirtualAlloc(NULL,0x4000000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);assert(g_module_base);
    *(uintptr_t *)(g_module_base+0x3809030)=(uintptr_t)nodes[0];
    nodes[0][232/8]=(uintptr_t)nodes[1];nodes[1][192/8]=(uintptr_t)nodes[2];nodes[2][136/8]=(uintptr_t)nodes[3];nodes[3][472/8]=(uintptr_t)page;
    vtable[1]=(uintptr_t)execute;backend[0]=(uintptr_t)vtable;names[0]=(uintptr_t)backend;name_service=(unsigned char *)names;
    *(uintptr_t *)career=(uintptr_t)vtable;*(uintptr_t *)(career+0x18)=(uintptr_t)contexts;
    *(int *)(contexts+0x1a4)=1043;*(int *)(contexts+0x18c)=1;
    mock_calendar=cal;((int *)(cal+0x34))[0]=11;((int *)(cal+0x34))[1]=1;((int *)(cal+0x34))[2]=2026;
    Fifa16CareerContextRead=(CareerContextRead){1,sizeof(CareerContextRead),2,GetCurrentProcessId(),(uintptr_t)career,(uintptr_t)vtable,123,2,GetCurrentThreadId()};
    native_name_db=(NativeNameDbApi){q_init,q_where,r_init,r_count,r_int,NULL,release,release};
    stable=0;drain_market_read();assert(!queries);
    strcpy(page,"game/screens/fluxHub/FluxHub");drain_market_read();strcpy(page,"game/screens/career/server16/TransferMarket");stable=1;
    ++Fifa16CareerContextRead.owner_thread;drain_market_read();assert(!queries);--Fifa16CareerContextRead.owner_thread;
    strcpy(page,"game/screens/fluxHub/FluxHub");drain_market_read();strcpy(page,"game/screens/career/server16/TransferMarket");
    drain_market_read();assert(queries==4);f=fopen(file,"rb");assert(f);n=fread(buffer,1,sizeof(buffer)-1,f);fclose(f);buffer[n]=0;
    assert(strstr(buffer,"complete=1") && strstr(buffer,"date=20260111") && strstr(buffer,"offer=12,32,7000000,1,1043") && strstr(buffer,"link=234,1043"));
    DeleteFileA(file);strcpy(page,"game/screens/fluxHub/FluxHub");drain_market_read();strcpy(page,"game/screens/career/server16/TransferMarket");mode=1;drain_market_read();assert(GetFileAttributesA(file)==INVALID_FILE_ATTRIBUTES);
    strcpy(page,"game/screens/fluxHub/FluxHub");drain_market_read();strcpy(page,"game/screens/career/server16/TransferMarket");mode=2;drain_market_read();assert(GetFileAttributesA(file)==INVALID_FILE_ATTRIBUTES);
    {char manager_folder[MAX_PATH],league_file[MAX_PATH];int before;
     snprintf(manager_folder,sizeof(manager_folder),"%s\\runtime\\manager_market",g_mod_dir);assert(CreateDirectoryA(manager_folder,NULL));
     snprintf(league_file,sizeof(league_file),"%s\\live_leagues.tsv",manager_folder);
     mode=0;Fifa16CareerContextRead.sequence=2;strcpy(page,"game/screens/fluxHub/FluxHub");
     before=queries;g_manager_read_next=0;drain_manager_read();assert(queries==before);
     manager_request=(PreparedViewRecord){1,GetCurrentProcessId(),1043,2,0,(uintptr_t)contexts,123,GetTickCount64(),20260111,0,{0}};manager_request_enabled=1;
     stable=0;drain_manager_calendar();assert(campaign_archives==1 && queries==before);stable=1;
     ++Fifa16CareerContextRead.owner_thread;g_manager_read_next=0;drain_manager_read();assert(queries==before);--Fifa16CareerContextRead.owner_thread;
     manager_request.captured=GetTickCount64()+100000;g_manager_read_next=0;drain_manager_read();assert(queries==before);manager_request.captured=GetTickCount64();
     g_current_stats_provider_owner=(void *)1;g_manager_read_next=0;drain_manager_read();assert(queries==before);g_current_stats_provider_owner=NULL;
     g_manager_read_next=0;drain_manager_read();assert(queries==before+1);f=fopen(league_file,"rb");assert(f);n=fread(buffer,1,sizeof(buffer)-1,f);fclose(f);buffer[n]=0;assert(strstr(buffer,"complete=1") && strstr(buffer,"league=") && strstr(buffer,"date=20260111"));
     {
       char days[MAX_PATH],scope[MAX_PATH],archived[MAX_PATH];int observed;
       snprintf(days,sizeof(days),"%s\\league_days",manager_folder);
       snprintf(scope,sizeof(scope),"%s\\%lu-%llu-%u-%llx",days,manager_request.pid,manager_request.created,manager_request.epoch,manager_request.context);
       snprintf(archived,sizeof(archived),"%s\\20260111.tsv",scope);assert(GetFileAttributesA(archived)!=INVALID_FILE_ATTRIBUTES);
       /* The old request day cannot suppress a new native calendar day,
        * even when the normal same-day refresh timer has not elapsed. */
       observed=queries;((int *)(cal+0x34))[0]=12;g_manager_read_next=GetTickCount64()+10000;drain_manager_read();assert(queries==observed+1);
       f=fopen(league_file,"rb");assert(f);n=fread(buffer,1,sizeof(buffer)-1,f);fclose(f);buffer[n]=0;assert(strstr(buffer,"date=20260112"));
       assert(DeleteFileA(archived));snprintf(archived,sizeof(archived),"%s\\20260112.tsv",scope);assert(DeleteFileA(archived));assert(RemoveDirectoryA(scope));assert(RemoveDirectoryA(days));
       ((int *)(cal+0x34))[0]=11;
     }
     DeleteFileA(league_file);mode=1;g_manager_read_next=0;drain_manager_read();assert(GetFileAttributesA(league_file)==INVALID_FILE_ATTRIBUTES);
     mode=2;g_manager_read_next=0;drain_manager_read();assert(GetFileAttributesA(league_file)==INVALID_FILE_ATTRIBUTES);assert(RemoveDirectoryA(manager_folder));
    }
    VirtualFree(g_module_base,0,MEM_RELEASE);*strrchr(file,'\\')=0;assert(RemoveDirectoryA(file));*strrchr(file,'\\')=0;assert(RemoveDirectoryA(file));*strrchr(file,'\\')=0;assert(RemoveDirectoryA(file));assert(RemoveDirectoryA(g_mod_dir));
    puts("PASS: live transfers and global coach league reads, scoped current date, native owner thread, bounds, atomic publication and rejection after a context change");return 0;
}
