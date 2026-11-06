#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../src/core/fce_runtime.h"
static FceModel preview_model;
FceLiveSnapshot *fce_runtime_cached_acquire(void) {return (FceLiveSnapshot *)&preview_model;}
const FceModel *fce_runtime_model(const FceLiveSnapshot *snapshot) {return (const FceModel *)snapshot;}
void fce_runtime_release(FceLiveSnapshot *snapshot) {(void)snapshot;}
static unsigned char *g_module_base;
static char g_mod_dir[MAX_PATH];
static void *g_pending_stats_provider_owner,*g_current_stats_provider_owner;
static void *g_pending_stats_provider_vtable,*g_pending_stats_provider_registry,*provider[2];
static struct { ULONGLONG entered_at; } g_stats_refresh_schedule;
static uintptr_t g_pending_stats_hub_view=1;
static unsigned long g_pending_stats_context_epoch=7;
static DWORD g_pending_stats_thread;
static int today=20261231,stable=1,logs,added,converted,literal;
__declspec(align(4096)) static unsigned char mail[4096],service[4096],context[4096];
__declspec(align(4096)) static uintptr_t registry[512];
static uintptr_t entries[8],empty_entries[1],calendar_pointer,mail_pointer;
__declspec(align(4096)) static unsigned char loan_calendar[4096];
static void *allocator_vtable[4],*allocator;
typedef void (*GetServiceDescriptorFn)(void *);
static int is_readable_range(const void *p,size_t size) {
    MEMORY_BASIC_INFORMATION info;
    return p && VirtualQuery(p,&info,sizeof(info)) && info.State==MEM_COMMIT
        && !(info.Protect&(PAGE_NOACCESS|PAGE_GUARD))
        && (uintptr_t)p+size<=(uintptr_t)info.BaseAddress+info.RegionSize;
}
static unsigned long fce_runtime_context_epoch(void) {return 7;}
static int fce_runtime_is_stable(void) {return stable;}
static uintptr_t current_card_hub_view(void) {return 1;}
static int native_calendar_date(void *owner) {(void)owner;return today;}
static void *owner_service(void *owner,GetServiceDescriptorFn descriptor,void *index) {
    (void)owner;(void)descriptor;(void)index;return mail;
}
static void append_loader_log(const char *line) {(void)line;++logs;}
static int read_card_scope(uintptr_t at,void *out,size_t size) {
    SIZE_T got=0;return ReadProcessMemory(GetCurrentProcess(),(void *)at,out,size,&got) && got==size;
}
#include "../../src/host/career_context_read.inc"
#include "../../src/host/career_bank_mail.inc"
#include "../../src/host/career_relay_page.h"
#include "../../src/host/career_bank_input.inc"
#include "../../src/host/career_preview_refresh.inc"
static int reloads;
static char *preview_page_name;
static void preview_event(void *bridge,const char *controller,const char *event,const char *argument) {
    assert(bridge && GetCurrentThreadId()==Fifa16CareerContextRead.owner_thread);
    assert(!strcmp(controller,"Calendar"));
    assert(!strcmp(event,"Server16RefreshMatchPreview") && !*argument);++reloads;
    strcpy(preview_page_name,"game/screens/career/server16/MatchPreview");
}
static void *get_allocator(void) {return &allocator;}
static void *allocate(void *self,size_t size,const char *name,int flags) {
    (void)self;assert(!strcmp(name,"Server16 bank mail") && flags==1);return calloc(1,size);
}
static void release(void *self,void *p,int flags) {(void)self;(void)flags;free(p);}
static void *construct(void *raw) {return raw;}
static void set_string(void *object,void *field,const char *text) {
    (void)object;*(char **)field=_strdup(text);
}
static void set_text(void *object,void *field,const char *text) {
    (void)object;*(const char **)field=text;++literal;
}
static void stock_convert(void *manager,void *destination,void *raw) {
    (void)manager;(void)destination;(void)raw;++converted;
}
static void insert(void *manager,int user,unsigned char *raw) {
    unsigned char rendered[64]={0};
    assert(GetCurrentThreadId()==g_pending_stats_thread && manager==mail && user==0);
    assert(*(int *)raw==1 && *(int *)(raw+4)==1 && *(int *)(raw+8)==1629);
    assert(*(int *)(raw+0x90)==20270101 && raw[0x9a]==1 && raw[0x9b]==1);
    assert(*(void **)(raw+0x10) && *(void **)(raw+0x20) && *(void **)(raw+0x28));
    assert(*(uintptr_t *)(*(uintptr_t *)(raw+0x10))==(uintptr_t)g_module_base+0x3031850);
    assert(*(int *)(*(uintptr_t *)(raw+0x10)+0x10)==1);
    bank_mail_convert(manager,rendered,raw);
    assert(!strcmp(*(const char **)(rendered+0x18),"Empr\xc3\xa9stimo aprovado"));
    assert(!strcmp(*(const char **)(rendered+0x20),"Antes 20.000.000; depois 21.000.000"));
    entries[added++]=(uintptr_t)raw;*(uintptr_t *)(mail+0x58)=(uintptr_t)(entries+added);
}
static void trampoline(unsigned rva,void *fn,const unsigned char *prefix) {
    unsigned char jump[]={0x48,0xb8,0,0,0,0,0,0,0,0,0xff,0xe0};uintptr_t target=(uintptr_t)fn;
    assert(VirtualAlloc(g_module_base+(rva&~4095u),4096,MEM_COMMIT,PAGE_EXECUTE_READWRITE));
    if (prefix) {memcpy(g_module_base+rva,prefix,5);rva+=5;}
    memcpy(jump+2,&target,8);memcpy(g_module_base+rva,jump,sizeof(jump));
}
static void request_file(const char *path,unsigned epoch) {
    FILE *f=fopen(path,"wb");const char *s="Empr\xc3\xa9stimo aprovado",*b="Antes 20.000.000; depois 21.000.000";
    assert(f);fprintf(f,"schema=1\npid=%lu\nclub=1629\ndue=20270101\ncontext=%llx\nepoch=%u\nid=%064d\nsubject=",GetCurrentProcessId(),(unsigned long long)(uintptr_t)context,epoch,1);
    while(*s)fprintf(f,"%02x",(unsigned char)*s++);fprintf(f,"\nbody=");
    while(*b)fprintf(f,"%02x",(unsigned char)*b++);fprintf(f,"\n");fclose(f);
}
static DWORD WINAPI wrong_thread(void *p) {(void)p;drain_bank_mail();return 0;}
static void preview_test(void) {
    unsigned char *nodes=VirtualAlloc(NULL,0x5000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    char path[MAX_PATH];FILE *f;uintptr_t nav_wrapper,calendar_wrapper;unsigned index=27,calendar_index=12;size_t i;
    FceFixture fixture={42,0,0,20270102,1600,1629,100,0,0,0,0};
    static const unsigned char head[]={0x48,0x89,0x5c,0x24,0x08};
    assert(nodes);assert(VirtualAlloc(g_module_base+0x3809000,4096,MEM_COMMIT,PAGE_READWRITE));
    *(void **)(g_module_base+0x3809030)=nodes;
    *(void **)(nodes+232)=nodes+0x400;*(void **)(nodes+0x400+192)=nodes+0x800;
    *(void **)(nodes+0x800+136)=nodes+0xc00;*(void **)(nodes+0xc00+472)=nodes+0x1000;
    preview_page_name=(char *)nodes+0x1000;strcpy(preview_page_name,"game/screens/career/server16/MatchPreviewLoading");
    assert(VirtualAlloc(g_module_base+0x4456000,4096,MEM_COMMIT,PAGE_READWRITE));
    memcpy(g_module_base+0x4456440+7,"\xc7\x01",2);memcpy(g_module_base+0x4456440+9,&index,4);
    memcpy(g_module_base+0x44563f0+7,"\xc7\x01",2);memcpy(g_module_base+0x44563f0+9,&calendar_index,4);
    calendar_wrapper=(uintptr_t)nodes+0x3000;registry[(12*32+24)/8]=(uintptr_t)&calendar_wrapper;
    *(int *)(nodes+0x3000+0x34)=1;*(int *)(nodes+0x3000+0x38)=1;*(int *)(nodes+0x3000+0x3c)=2027;
    preview_model.fixtures=&fixture;preview_model.fixture_count=1;
    assert(VirtualAlloc(g_module_base+0x5ac2000,4096,MEM_COMMIT,PAGE_READWRITE));memcpy(g_module_base+0x5ac21a0,"\x48\x8b\x41\x50",4);
    trampoline(0x5ad2240,preview_event,head);
    assert(VirtualAlloc(g_module_base+0x3518000,4096,MEM_COMMIT,PAGE_READWRITE));
    assert(VirtualAlloc(g_module_base+0x21ae000,4096,MEM_COMMIT,PAGE_READWRITE));
    *(void **)(g_module_base+0x35188d0)=nodes+0x3500;
    *(void **)(nodes+0x3500)=g_module_base+0x21aeb40;
    *(void **)(g_module_base+0x21aeb40+0x28)=g_module_base+0x4047290;
    {static const unsigned char bridge_head[]={0x48,0x89,0x5c,0x24,0x10};trampoline(0x4047290,preview_event,bridge_head);}
    nav_wrapper=(uintptr_t)nodes+0x1800;registry[(27*32+24)/8]=(uintptr_t)&nav_wrapper;
    *(void **)(nodes+0x1800+8)=registry;*(void **)(nodes+0x1800+0x50)=nodes+0x2000;*(void **)(nodes+0x2000+19*8)=nodes+0x2800;
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\preview",g_mod_dir);assert(CreateDirectoryA(path,NULL));strcat(path,"\\runtime");assert(CreateDirectoryA(path,NULL));strcat(path,"\\native_refresh.tsv");
    f=fopen(path,"wb");assert(f);fprintf(f,"schema=2\ndate=20270101\nfixture=42\npid=%lu\nclub=1629\ncontext=%llx\nrevision=",GetCurrentProcessId(),(unsigned long long)(uintptr_t)context);for(i=0;i<64;++i)fputc('a',f);fputc('\n',f);fclose(f);
    g_pending_stats_provider_owner=NULL;g_pending_stats_hub_view=0;
    stable=0;drain_preview_refresh();assert(!reloads);stable=1;
    Fifa16CareerContextRead.owner_thread=0;drain_preview_refresh();assert(!reloads);Fifa16CareerContextRead.owner_thread=GetCurrentThreadId();
    strcpy((char *)nodes+0x1000,"game/screens/career/Calendar");drain_preview_refresh();assert(!reloads);
    strcpy(preview_page_name,"game/screens/career/server16/MatchPreviewLoading");drain_preview_refresh();assert(reloads==1);
    Sleep(550);drain_preview_refresh();assert(reloads==1);
    /* The old package must remain hidden after a calendar advance. */
    *(int *)(nodes+0x3000+0x34)=2;strcpy(preview_page_name,"game/screens/career/server16/MatchPreviewLoading");
    Sleep(550);drain_preview_refresh();assert(reloads==1);
    f=fopen(path,"wb");assert(f);fprintf(f,"schema=2\ndate=20270102\nfixture=42\npid=%lu\nclub=1629\ncontext=%llx\nrevision=",GetCurrentProcessId(),(unsigned long long)(uintptr_t)context);for(i=0;i<64;++i)fputc('b',f);fputc('\n',f);fclose(f);
    Sleep(550);drain_preview_refresh();assert(reloads==2);
    fixture.id=43;strcpy(preview_page_name,"game/screens/career/server16/MatchPreviewLoading");
    Sleep(550);drain_preview_refresh();assert(reloads==2);
    assert(DeleteFileA(path));*strrchr(path,'\\')=0;assert(RemoveDirectoryA(path));*strrchr(path,'\\')=0;assert(RemoveDirectoryA(path));assert(VirtualFree(nodes,0,MEM_RELEASE));
}
static void set_today(int value) {
    today=value;*(int *)(loan_calendar+0x34)=value%100;
    *(int *)(loan_calendar+0x38)=(value/100)%100;*(int *)(loan_calendar+0x3c)=value/10000;
}
static int original_events;
static uintptr_t original_event(void *bridge,const char *controller,const char *event,const char *argument) {
    assert(bridge && !strcmp(controller,"OriginalController"));
    assert(!strcmp(event,"StockEvent") && !strcmp(argument,"original argument"));
    ++original_events;return 0x123456789abcdef0ull;
}
static DWORD WINAPI input_from_apt_thread(void *wire) {return (DWORD)bank_input_capture((const char *)wire);}
static void bank_input_test(void) {
    unsigned char *nodes=VirtualAlloc(NULL,0x3000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    char wire[512],path[MAX_PATH],line[1024];void *vtable[6]={0},*bridge=vtable;FILE *f;int matched=0;
    uintptr_t (*call)(void *,const char *,const char *,const char *);
    assert(nodes);assert(VirtualAlloc(g_module_base+0x3809000,4096,MEM_COMMIT,PAGE_READWRITE));
    *(void **)(g_module_base+0x3809030)=nodes;
    *(void **)(nodes+232)=nodes+0x400;*(void **)(nodes+0x400+192)=nodes+0x800;
    *(void **)(nodes+0x800+136)=nodes+0xc00;*(void **)(nodes+0xc00+472)=nodes+0x1000;
    strcpy((char *)nodes+0x1000,"game/screens/career/server16/BankLoansV2");
    set_today(20270104);
    snprintf(wire,sizeof(wire),"S16BANK_V3|B57_%lu_1629_012345abcdef|1|0|9|2|1|20270101|END_S16BANK",GetCurrentProcessId());
    assert(bank_input_capture(wire));
    {DWORD result=0;HANDLE thread=CreateThread(NULL,0,input_from_apt_thread,wire,0,NULL);
     assert(thread && WaitForSingleObject(thread,5000)==WAIT_OBJECT_0);
     assert(GetExitCodeThread(thread,&result) && result==1);CloseHandle(thread);}
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\bank\\runtime\\native_request.tsv",g_mod_dir);
    f=fopen(path,"rb");assert(f);while(fgets(line,sizeof(line),f))if(!strcmp(line,"date=20270104\n"))++matched;fclose(f);assert(matched==1);
    /* Finance switches share only the scoped click transport, not loan logic. */
    strcpy((char *)nodes+0x1000,"game/screens/career/server16/ClubFinance");assert(bank_input_capture(wire));
    strcpy((char *)nodes+0x1000,"game/screens/career/server16/ClubFinanceLoading");assert(!bank_input_capture(wire));
    strcpy((char *)nodes+0x1000,"game/screens/fluxHub/FluxHub");assert(!bank_input_capture(wire));
    strcpy((char *)nodes+0x1000,"game/screens/career/server16/BankLoansV2");
    assert(!bank_input_capture("S16BANK_V3|B57_999_1629_nonce|1|0|9|2|1|20270101|END_S16BANK"));
    assert(!bank_input_capture("S16BANK_V3|malformed\nwire|END_S16BANK"));
    vtable[5]=(void *)original_event;
    assert(bank_input_event(&bridge,"OriginalController","StockEvent","original argument")==0x123456789abcdef0ull);
    assert(original_events==1);
    /* A room event is isolated from stock/bank dispatch; a missing room
     * plugin is harmless and never invokes the Calendar stock handler. */
    assert(bank_input_event(&bridge,"Calendar","Server16RoomScene","S16ROOM2|1629|0123456789abcdef|1|-2|ENDROOM")==0);
    assert(original_events==1);
    /* Execute a tiny ABI-equivalent caller through the installed six-byte
     * call-site patch. All 17 existing DLL exports remain untouched. */
    assert(VirtualAlloc(g_module_base+0x4502000,4096,MEM_COMMIT,PAGE_EXECUTE_READWRITE));
    memcpy(g_module_base+0x4502dde,"\x48\x83\xec\x28\x48\x8b\x01\xff\x50\x28\x48\x83\xc4\x28\xc3",15);
    assert(install_bank_input_hook(NULL));assert(!install_bank_input_hook(NULL));
    call=(uintptr_t (*)(void *,const char *,const char *,const char *))(g_module_base+0x4502dde);
    assert(call(&bridge,"OriginalController","StockEvent","original argument")==0x123456789abcdef0ull);
    assert(original_events==2);
    assert(call(&bridge,"Calendar","Server16SubmitBank",wire)==0);
    assert(DeleteFileA(path));
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\bank\\runtime\\native_input_ready.tsv",g_mod_dir);assert(DeleteFileA(path));
    assert(VirtualFree(nodes,0,MEM_RELEASE));
}
int main(void) {
    char temporary[MAX_PATH],path[MAX_PATH],receipt[MAX_PATH];unsigned char raw[0x60]={0},rendered[64]={0};BankMailRequest request;HANDLE thread;
    static const unsigned char ctor[]={0x48,0x89,0x5c,0x24,0x08},add[]={0x48,0x89,0x7c,0x24,0x20};
    _set_abort_behavior(0,_CALL_REPORTFAULT);
    assert(sizeof(CareerContextRead)==48);
    g_module_base=VirtualAlloc(NULL,0x5c20000,MEM_RESERVE,PAGE_NOACCESS);assert(g_module_base);
    allocator_vtable[2]=(void *)allocate;allocator_vtable[3]=(void *)release;allocator=allocator_vtable;
    trampoline(0x44679b0,get_allocator,NULL);trampoline(0x5b4af80,construct,ctor);trampoline(0x5b569e0,insert,add);
    trampoline(0x5c152c0,set_string,NULL);trampoline(0x5c15210,set_text,NULL);trampoline(0x5c12860,stock_convert,NULL);
    *(void **)(raw+0x48)="CM_Email_Board_Subject";*(void **)(raw+0x58)="CM_Email_Board_Body";
    bank_mail_convert(mail,rendered,raw);assert(converted==1 && !literal);
    *(void **)(raw+0x48)="S16BANKMAIL:not_a_valid_id|stock";bank_mail_convert(mail,rendered,raw);assert(converted==2 && !literal);
    assert(GetTempPathA(sizeof(temporary),temporary));assert(GetTempFileNameA(temporary,"s16",0,g_mod_dir));assert(DeleteFileA(g_mod_dir));assert(CreateDirectoryA(g_mod_dir,NULL));
    snprintf(path,sizeof(path),"%s\\runtime",g_mod_dir);assert(CreateDirectoryA(path,NULL));
    strcat(path,"\\club_environment");assert(CreateDirectoryA(path,NULL));strcat(path,"\\bank");assert(CreateDirectoryA(path,NULL));strcat(path,"\\runtime");assert(CreateDirectoryA(path,NULL));
    snprintf(receipt,sizeof(receipt),"%s\\native_mail_receipt.tsv",path);strcat(path,"\\native_mail_request.tsv");
    assert(VirtualAlloc(g_module_base+0x4456000,4096,MEM_COMMIT,PAGE_READWRITE));
    {unsigned cal=12,inbox=37;
     memcpy(g_module_base+0x44563f0+7,"\xc7\x01",2);memcpy(g_module_base+0x44563f0+9,&cal,4);
     memcpy(g_module_base+0x44565f0+7,"\xc7\x01",2);memcpy(g_module_base+0x44565f0+9,&inbox,4);
     calendar_pointer=(uintptr_t)loan_calendar;mail_pointer=(uintptr_t)mail;
     registry[(cal*32+24)/8]=(uintptr_t)&calendar_pointer;registry[(inbox*32+24)/8]=(uintptr_t)&mail_pointer;}
    set_today(20261231);
    *(void **)service=&logs;*(int *)(service+0x14)=0;*(void **)(service+0x18)=context;
    *(int *)(context+0x1a4)=1629;*(int *)(context+0x18c)=1;*(void **)(mail+8)=registry;
    *(void **)(mail+0x50)=entries;*(void **)(mail+0x58)=entries;
    *(void **)(mail+0x90)=empty_entries;*(void **)(mail+0x98)=empty_entries;
    provider[0]=&logs;provider[1]=registry;publish_career_context_read(service,provider);
    g_pending_stats_provider_owner=provider;g_pending_stats_provider_vtable=provider[0];g_pending_stats_provider_registry=registry;g_pending_stats_thread=GetCurrentThreadId();
    request_file(path,7);assert(bank_mail_read(path,&request));assert(!strcmp(request.subject,"Empr\xc3\xa9stimo aprovado"));
    {char output[8];assert(!bank_mail_unhex("0001",output,sizeof(output)));assert(!bank_mail_unhex("xx",output,sizeof(output)));}
    drain_bank_mail();assert(!added);set_today(20270101);Sleep(1050);
    request_file(path,8);drain_bank_mail();assert(!added);request_file(path,7);Sleep(1050);
    thread=CreateThread(NULL,0,wrong_thread,NULL,0,NULL);assert(thread && WaitForSingleObject(thread,5000)==WAIT_OBJECT_0);CloseHandle(thread);assert(!added);
    stable=0;drain_bank_mail();assert(!added);stable=1;
    /* Calendar skipped the original event day. The raw e-mail keeps Jan 1;
     * the delivery receipt below records the actual insertion on Jan 4. */
    set_today(20270104);
    /* Entering Loans invalidates these deferred hub identities. Mail still
     * runs on the verified current career owner, with no stale Stats calls. */
    g_pending_stats_provider_owner=NULL;g_pending_stats_hub_view=0;
    drain_bank_mail();
    if (!added) fprintf(stderr,"mail gate: pid=%lu epoch=%lu thread=%lu expected=%lu context=%llx requested=%llx read=%d date=%d exists=%d\n",Fifa16CareerContextRead.pid,Fifa16CareerContextRead.epoch,GetCurrentThreadId(),Fifa16CareerContextRead.owner_thread,(unsigned long long)(uintptr_t)context,(unsigned long long)request.context,bank_mail_read(path,&request),today,bank_mail_exists(mail,"absent"));
    if (!added) fprintf(stderr,"service=%llx stored=%llx sel=%d role=%d club=%u read_service=%d due=%u epoch=%u heads=%d/%d\n",(unsigned long long)(uintptr_t)service,(unsigned long long)Fifa16CareerContextRead.service,*(int *)(service+0x14),*(int *)(context+0x18c),*(unsigned *)(context+0x1a4),is_readable_range(service,32),request.due,request.epoch,memcmp(g_module_base+0x5b4af80,ctor,5),memcmp(g_module_base+0x5b569e0,add,5));
    assert(added==1 && literal==2 && logs==1);
    {char line[256];int actual=0;FILE *f=fopen(receipt,"rb");assert(f);
     while(fgets(line,sizeof(line),f))if(sscanf(line,"date=%d",&actual)==1)break;
     fclose(f);assert(actual==20270104);}
    Sleep(1050);drain_bank_mail();assert(added==1 && literal==2);assert(GetFileAttributesA(receipt)!=INVALID_FILE_ATTRIBUTES);
    assert(DeleteFileA(path));assert(DeleteFileA(receipt));
    {char status[MAX_PATH];snprintf(status,sizeof(status),"%s\\runtime\\club_environment\\bank\\runtime\\native_mail_status.tsv",g_mod_dir);assert(DeleteFileA(status));}
    bank_input_test();preview_test();
    {unsigned char *p=(unsigned char *)entries[0];free(*(void **)(p+0x48));free(*(void **)(p+0x58));free(*(void **)(p+0x10));free(*(void **)(p+0x20));free(*(void **)(p+0x28));free(p);}
    *strrchr(path,'\\')=0;assert(RemoveDirectoryA(path));*strrchr(path,'\\')=0;assert(RemoveDirectoryA(path));*strrchr(path,'\\')=0;assert(RemoveDirectoryA(path));*strrchr(path,'\\')=0;assert(RemoveDirectoryA(path));assert(RemoveDirectoryA(g_mod_dir));
    assert(VirtualFree(g_module_base,0,MEM_RELEASE));
    puts("PASS: synchronous scoped request capture, original event ABI/delegation, stock mail delegation, owner-thread inbox insertion and deduplication, exact-view preview reload");return 0;
}
