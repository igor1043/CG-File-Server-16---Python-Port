#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "protocol.h"
typedef BOOL (*RegisterUiFn)(void (*)(void));
typedef unsigned char (*MenuEventFn)(void *,int);
typedef void (*GatherFn)(void *,int,int,int *);
typedef void (*AddFn)(void *,const int *,int);
typedef void (*InformFn)(void *,int *,unsigned char);
typedef void (*WithdrawFn)(void *,int);
typedef struct Profile { uintptr_t registry,context; int club; unsigned char *manager; void *standings; unsigned char *menu; } Profile;
static unsigned char *game;
static uintptr_t *owner_global,*owner_vtable;
static HMODULE native_module;
static JobsShared *shared;
static MenuEventFn menu_event;
static GatherFn gather;
static AddFn add_offer;
static InformFn inform;
static WithdrawFn withdraw_offer;
static uintptr_t bound_registry,bound_context;
static int bound_club;
static uint32_t bound_epoch;
static int pending_contract_seq,pending_contract_team,pending_contract_league;
static uint32_t pending_contract_tick;
static LONG processing;
static char log_path[MAX_PATH],bridge_path[MAX_PATH],disable_path[MAX_PATH];
__declspec(dllexport) const uint32_t Fifa16CareerJobsProtocol=JOBS_VERSION;

static void log_event(const char *event,int team,int league,int count)
{
    FILE *f;if(!log_path[0])return;
    f=fopen(log_path,"ab");if(!f)return;
    fprintf(f,"pid=%lu tick=%llu event=%s team=%d league=%d count=%d\n",
        (unsigned long)GetCurrentProcessId(),(unsigned long long)GetTickCount64(),event,team,league,count);
    fclose(f);
}
static int readable(const void *p,SIZE_T n)
{
    MEMORY_BASIC_INFORMATION m;uintptr_t a=(uintptr_t)p,end=a+n;
    if(!a || end<a)return 0;
    while(a<end) {
        if(!VirtualQuery((void *)a,&m,sizeof(m)) || m.State!=MEM_COMMIT
            || (m.Protect&(PAGE_NOACCESS|PAGE_GUARD)))return 0;
        if((uintptr_t)m.BaseAddress+m.RegionSize<=a)return 0;
        a=(uintptr_t)m.BaseAddress+m.RegionSize;
    }
    return 1;
}
static void *service(uintptr_t registry,int index)
{
    uintptr_t *p=(uintptr_t *)(registry+(uintptr_t)index*32U+24U);
    if(!readable(p,sizeof(*p)) || !readable((void *)*p,sizeof(uintptr_t)))return NULL;
    return *(void **)*p;
}
static int current_profile(Profile *p)
{
#ifdef CAREER_JOBS_TEST
    extern Profile mocked_profile;
    *p=mocked_profile;return 1;
#else
    uintptr_t owner,career,contexts;int index,selected;
    if(!owner_global || !owner_vtable || !readable(owner_global,8) || !readable(owner_vtable,8))return 0;
    owner=*owner_global;
    if(!readable((void *)owner,16) || *(uintptr_t *)owner!=*owner_vtable)return 0;
    p->registry=*(uintptr_t *)(owner+8);
    memcpy(&index,game+0x044575e0+9,4);
    if(index<0 || index>256)return 0;
    career=(uintptr_t)service(p->registry,index);
    if(!readable((void *)career,32))return 0;
    selected=*(int *)(career+0x14);contexts=*(uintptr_t *)(career+0x18);
    if(selected<0 || selected>7)return 0;
    p->context=contexts+(uintptr_t)selected*0x318U;
    if(!readable((void *)p->context,0x318) || *(int *)(p->context+0x18c)!=1)return 0;
    p->club=*(int *)(p->context+0x1a4);
    p->manager=(unsigned char *)service(p->registry,54);
    p->standings=service(p->registry,*(int *)(game+0x044570e0+9));
    p->menu=(unsigned char *)service(p->registry,26);
    return p->club>0 && p->club<2000000 && readable(p->manager,0x188)
        && *(uintptr_t *)p->manager==(uintptr_t)(game+0x03071270)
        && *(uintptr_t *)(p->manager+0x150)==(uintptr_t)(game+0x03071250)
        && p->standings;
#endif
}
static int *find_offer(unsigned char *manager,int team,int league)
{
    uintptr_t first=*(uintptr_t *)(manager+0xd8),last=*(uintptr_t *)(manager+0xe0),at;
    if(last<first || last-first>4096U*32U || (last-first)%32U || !readable((void *)first,last-first))return NULL;
    for(at=first;at<last;at+=32U)if(*(int *)at==team && *(int *)(at+4)==league)return (int *)at;
    return NULL;
}
static int ensure_offer(Profile *p,int team,int league)
{
    int record[10],i;
    if(find_offer(p->manager,team,league))return 1;
    for(i=0;i<10;++i)record[i]=-1;
    gather(p->standings,team,*(int *)(p->manager+0x144),record);
    if(record[4]!=team)return 0;
    add_offer(p->manager,record,league);
    return find_offer(p->manager,team,league)!=NULL;
}
static void scope_profile(const Profile *p)
{
    if(bound_registry!=p->registry || bound_context!=p->context || bound_club!=p->club || bound_epoch!=shared->load_epoch) {
        if(pending_contract_seq) {
            shared->error=1;shared->status=-1;shared->completed=pending_contract_seq;
            pending_contract_seq=0;
        }
        bound_registry=p->registry;bound_context=p->context;
        bound_club=p->club;bound_epoch=shared->load_epoch;shared->count=0;
        memset(shared->clubs,0,sizeof(shared->clubs));
    }
}
static int enter_contract(Profile *p)
{
    int *offer=(int *)(p->manager+0x158);
    if(!pending_contract_seq)return 1;
    if((uint32_t)(GetTickCount()-pending_contract_tick)>90000U) {
        shared->error=8;shared->status=-1;pending_contract_seq=0;return -1;
    }
    if(offer[0]!=pending_contract_team || offer[1]!=pending_contract_league
        || offer[6]<0 || offer[7]<=0 || offer[10]>0) {
        shared->error=7;shared->status=-1;pending_contract_seq=0;return -1;
    }
    if(!readable(p->menu,0x1350)
        || *(uintptr_t *)p->menu!=(uintptr_t)(game+0x0304bfe8)
        || *(uintptr_t *)(p->menu+8)!=p->registry
        || *(uintptr_t *)(p->menu+0x1348)!=p->registry)return 0;
    if(!p->menu[0x20] || p->menu[0x10])return 0;
    /* This is the same queued native transition as the offer email's
     * View Offer action. It opens FIFA's contract decision; it never accepts. */
    if(!menu_event(p->menu,-9911))return 0;
    if(!p->menu[0x10] || !*(uintptr_t *)(p->menu+0x18)) {
        shared->error=9;shared->status=-1;pending_contract_seq=0;return -1;
    }
    log_event("native_contract_entry_queued",pending_contract_team,pending_contract_league,pending_contract_seq);
    pending_contract_seq=0;
    MemoryBarrier();InterlockedExchange((LONG *)&shared->status,1);
    return 1;
}
static void process_profile(Profile *p)
{
    int seq,*offer=(int *)(p->manager+0x158),*row,details[8],previous_team,previous_application,valid_days;
    JobsShared command;
    scope_profile(p);
    if(pending_contract_seq) {enter_contract(p);return;}
    seq=shared->sequence;
    if(seq==shared->completed)return;
    MemoryBarrier();memcpy(&command,shared,sizeof(command));MemoryBarrier();
    if(seq!=shared->sequence)return;
    shared->status=0;shared->error=0;
    if(!jobs_request_valid(&command,p->club,p->registry,p->context))shared->error=1;
    else if((uint32_t)(GetTickCount()-command.reserved)>90000U)shared->error=8;
    else {
        if(!ensure_offer(p,command.team,command.league))shared->error=2;
        else {
            row=find_offer(p->manager,command.team,command.league);
            if(!row || row[7]<=0)shared->error=2;
            else {
                /* Validate/build the destination BEFORE touching the prior
                 * offer. Archive its actionable email through FIFA's own
                 * withdrawal routine, also used by ordinary ApplyJob. */
                memcpy(details,row,sizeof(details));
                previous_team=offer[0];previous_application=offer[8];
                if(previous_team>0) {
                    withdraw_offer(p->manager,previous_team);
                    log_event("previous_proposal_archived",previous_team,offer[1],command.team);
                }
                if(previous_application>0)
                    log_event("previous_application_replaced",previous_application,0,command.team);
                memcpy(offer,details,sizeof(details));
                offer[6]=-1;offer[8]=offer[9]=offer[10]=-1;
                /* Consume the sequence BEFORE posting the native event: an
                 * event listener may reenter StatisticsData. Never dispatch
                 * mail inside BrowseJobs/ApplyJob UI callbacks. */
                InterlockedExchange((LONG *)&shared->completed,seq);
                inform(p->manager,offer,1);
                if(offer[0]==command.team && offer[1]==command.league
                    && offer[6]>=0 && offer[7]>0 && offer[10]==-1) {
                    shared->count=1;memset(shared->clubs,0,sizeof(shared->clubs));
                    shared->clubs[0][0]=command.team;shared->clubs[0][1]=command.league;
                    valid_days=*(int *)(p->manager+0x14);
                    shared->reserved=(valid_days>0 && valid_days<=365)?(uint32_t)valid_days:0;
                    log_event("proposal_created",command.team,command.league,offer[7]);
                    pending_contract_seq=seq;pending_contract_team=command.team;pending_contract_league=command.league;
                    pending_contract_tick=command.reserved;
                    enter_contract(p);
                } else shared->error=6;
            }
        }
    }
    if(shared->error) {
        if(shared->error==6)shared->ready=0;
        shared->status=-1;log_event("request_rejected",command.team,command.league,(int)shared->error);
    }
    MemoryBarrier();InterlockedExchange((LONG *)&shared->completed,seq);
}
static int contract_hub(void)
{
#ifdef CAREER_JOBS_TEST
    extern int mocked_hub;
    return mocked_hub;
#else
    static const unsigned offsets[]={232,192,136,472};
    static const unsigned started_offsets[]={560,1592,88,16};
    uintptr_t pointer;unsigned i;char page[80];
    pointer=*(uintptr_t *)(game+0x03809030);
    for(i=0;i<4;++i) {
        if(!readable((void *)(pointer+offsets[i]),8))return 0;
        pointer=*(uintptr_t *)(pointer+offsets[i]);
    }
    if(!readable((void *)pointer,sizeof(page)))return 0;
    memcpy(page,(void *)pointer,sizeof(page));page[sizeof(page)-1]=0;
    if(strcmp(page,"game/screens/fluxHub/FluxHub")
        && strcmp(page,"game/screens/career/CareerHub")
        && strcmp(page,"game/screens/career/Home"))return 0;
    pointer=*(uintptr_t *)(game+0x034eb830);
    for(i=0;i<4;++i) {
        if(!readable((void *)(pointer+started_offsets[i]),8))return 0;
        pointer=*(uintptr_t *)(pointer+started_offsets[i]);
    }
    if(!readable((void *)(pointer+4056),4))return 0;
    return *(int *)(pointer+4056)==0;
#endif
}
static void process_current(void)
{
    Profile p;
    if(!shared || !shared->ready || InterlockedCompareExchange(&processing,1,0))return;
    __try { if(current_profile(&p) && contract_hub())process_profile(&p); }
    __except(EXCEPTION_EXECUTE_HANDLER) {
        shared->error=6;shared->status=-1;shared->completed=shared->sequence;
        shared->ready=0;log_event("delivery_failed_disabled",0,0,6);
    }
    InterlockedExchange(&processing,0);
}
static int initialize(void)
{
    static const unsigned char marker[]={0x48,0x8d,0x54,0x24,0x50,0x48,0x8d,0x4c,0x24,0x40,0xe8};
    unsigned char *entry,*live;uintptr_t names;const char *event_name;RegisterUiFn register_ui;
    int i,a=-1,b=-1;int32_t relative;
    HMODULE m=NULL,modules[512];DWORD needed,k;
    entry=NULL;
    if(!EnumProcessModules(GetCurrentProcess(),modules,sizeof(modules),&needed))return 0;
    for(k=0;k<needed/sizeof(HMODULE) && k<512;++k) {
        entry=(unsigned char *)GetProcAddress(modules[k],"Fifa16CareerGetState");
        if(entry) {m=modules[k];break;}
    }
    if(!m || !entry)return 0;
    register_ui=(RegisterUiFn)GetProcAddress(m,"Fifa16CareerRegisterJobUiCallback");
    if(!register_ui)return -1;
    native_module=m;game=(unsigned char *)GetModuleHandleW(NULL);
    for(i=0;i<80;++i)if(!memcmp(entry+i,marker,sizeof(marker)))break;
    if(i==80)return 0;
    memcpy(&relative,entry+i+11,4);live=entry+i+15+relative;
    for(i=0;i<50;++i) {
        if(!memcmp(live+i,"\x48\x8b\x3d",3))a=i;
        if(!memcmp(live+i,"\x48\x8b\x35",3))b=i;
    }
    if(a<0 || b<0)return 0;
    memcpy(&relative,live+a+3,4);owner_global=(uintptr_t *)(live+a+7+relative);
    memcpy(&relative,live+b+3,4);owner_vtable=(uintptr_t *)(live+b+7+relative);
    if(memcmp(game+0x05aa4120,"\x48\x89\x5c\x24\x18",5)
        || memcmp(game+0x05b57860,"\x48\x89\x5c\x24\x08",5)
        || memcmp(game+0x05bcfaa0,"\x48\x89\x5c\x24\x08",5)
        || memcmp(game+0x05b5c730,"\x48\x89\x5c\x24\x18",5))return 0;
    if(memcmp(game+0x05b06bd0,"\x48\x83\xec\x28\x80\x79\x20\x00",8)
        || memcmp(game+0x05b06c9e,"\x48\x8d\x1d",3))return -1;
    memcpy(&relative,game+0x05b06ca1,4);names=(uintptr_t)(game+0x05b06ca5)+relative;
    names-=(uintptr_t)9911*8;
    if(!readable((void *)names,8))return -1;
    event_name=*(const char **)names;
    if(!readable(event_name,sizeof("EnterJobOfferSign"))
        || memcmp(event_name,"EnterJobOfferSign",sizeof("EnterJobOfferSign")))return -1;
    gather=(GatherFn)(game+0x05aa4120);add_offer=(AddFn)(game+0x05b57860);
    inform=(InformFn)(game+0x05bcfaa0);
    withdraw_offer=(WithdrawFn)(game+0x05b5c730);
    menu_event=(MenuEventFn)(game+0x05b06bd0);
    /* No game CALL sites are patched. The host invokes this only after the
     * normal engine update has completed and its career model is stable. */
    if(!register_ui(process_current))return -1;
    return 1;
}
static DWORD WINAPI worker(void *unused)
{
    wchar_t name[100];HANDLE mapping,instance;char exe[MAX_PATH],*slash,line[1400],operation[20];
    unsigned long long tick,last_tick=0;unsigned long pid;FILE *f;int tries,result=0;
    (void)unused;GetModuleFileNameA(NULL,exe,MAX_PATH);slash=strrchr(exe,'\\');if(!slash)return 0;*slash=0;
    snprintf(log_path,sizeof(log_path),"%s\\ModCarrerMode\\logs\\career_jobs_runtime.log",exe);
    snprintf(bridge_path,sizeof(bridge_path),"%s\\ModCarrerMode\\runtime\\career_save_source.tsv",exe);
    snprintf(disable_path,sizeof(disable_path),"%s\\ModCarrerMode\\config\\career_live_jobs.disabled",exe);
    if(GetFileAttributesA(disable_path)!=INVALID_FILE_ATTRIBUTES)return 0;
    swprintf_s(name,100,L"Local\\FIFA16CareerJobsOwner_%lu",(unsigned long)GetCurrentProcessId());
    instance=CreateMutexW(NULL,FALSE,name);
    if(!instance)return 0;
    if(GetLastError()==ERROR_ALREADY_EXISTS) {CloseHandle(instance);return 0;}
    /* Keep the ownership handle for process lifetime. A duplicate DLL must
     * never clear the channel belonging to the first instance. */
    swprintf_s(name,100,L"Local\\FIFA16CareerJobs_v%u_%lu",JOBS_VERSION,(unsigned long)GetCurrentProcessId());
    mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,NULL,PAGE_READWRITE,0,sizeof(JobsShared),name);
    if(!mapping)return 0;
    shared=(JobsShared *)MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(JobsShared));if(!shared)return 0;
    memset(shared,0,sizeof(*shared));shared->magic=JOBS_MAGIC;shared->version=JOBS_VERSION;
    shared->pid=GetCurrentProcessId();shared->load_epoch=1;
    for(tries=0;tries<120 && !result;++tries) {result=initialize();if(!result)Sleep(500);}
    if(result!=1) {shared->error=10;log_event("hook_install_failed",0,0,result);return 0;}
    shared->ready=1;log_event("native_contract_ui_ready",0,0,JOBS_VERSION);
    for(;;) {
        if(GetFileAttributesA(disable_path)!=INVALID_FILE_ATTRIBUTES)shared->ready=0;
        shared->heartbeat=GetTickCount();tick=0;pid=0;operation[0]=0;
        f=fopen(bridge_path,"rb");
        if(f) {
            while(fgets(line,sizeof(line),f)) {
                if(!strncmp(line,"pid=",4))sscanf_s(line+4,"%lu",&pid);
                if(!strncmp(line,"access_tick_ms=",15))sscanf_s(line+15,"%llu",&tick);
                if(!strncmp(line,"operation=",10))sscanf_s(line+10,"%19s",operation,(unsigned)sizeof(operation));
            }
            fclose(f);
            if(pid==GetCurrentProcessId() && !strcmp(operation,"read") && tick && tick!=last_tick) {
                if(last_tick)InterlockedIncrement((LONG *)&shared->load_epoch);
                last_tick=tick;
            }
        }
        Sleep(500);
    }
}
#ifndef CAREER_JOBS_TEST
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,void *reserved)
{
    HANDLE thread;(void)reserved;
    if(reason==DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);thread=CreateThread(NULL,0,worker,NULL,0,NULL);
        if(thread)CloseHandle(thread);
    }
    return TRUE;
}
#endif
