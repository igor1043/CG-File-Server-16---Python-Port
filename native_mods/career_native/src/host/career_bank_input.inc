/* Capture the loan screen's explicit system event, not an APT heap search.
 * Only this exact event is consumed. Every stock/foreign event retains the
 * original bridge dispatch, arguments and return value. No finance writes. */
static int bank_input_page(void)
{
    static const unsigned offsets[]={232,192,136,472};
    uintptr_t node=0;char page[96];unsigned i;
    if(!read_card_scope((uintptr_t)g_module_base+0x3809030,&node,8))return 0;
    for(i=0;i<4;++i)if(!node || !read_card_scope(node+offsets[i],&node,8))return 0;
    return node && read_card_scope(node,page,sizeof(page)) && memchr(page,0,sizeof(page))
        && (!strcmp(page,"game/screens/career/server16/BankLoansV2")
            || !strcmp(page,"game/screens/career/server16/ClubFinance"));
}

static int bank_input_context(CareerContextRead *out,uintptr_t *context,unsigned *club,int *date)
{
    uintptr_t contexts;unsigned char *calendar;int selected,parts[3];
    memcpy(out,&Fifa16CareerContextRead,sizeof(*out));
    if(out->schema!=1 || out->size!=sizeof(*out) || out->sequence&1
        || out->pid!=GetCurrentProcessId() || out->epoch!=fce_runtime_context_epoch()
        || !is_readable_range((void *)out->service,32)
        || *(uintptr_t *)out->service!=out->vtable)return 0;
    selected=*(int *)(out->service+0x14);contexts=*(uintptr_t *)(out->service+0x18);
    if(selected<0 || selected>7 || !contexts)return 0;
    *context=contexts+(uintptr_t)selected*0x318;
    if(!is_readable_range((void *)*context,0x318) || *(int *)(*context+0x18c)!=1)return 0;
    *club=*(unsigned *)(*context+0x1a4);
    calendar=bank_mail_service(out->registry,0x44563f0,0x40);
    if(!*club || !calendar)return 0;
    memcpy(parts,calendar+0x34,sizeof(parts));*date=fce_date_pack(parts[0],parts[1],parts[2]);
    return fce_date_valid(*date) && Fifa16CareerContextRead.sequence==out->sequence;
}

static int bank_input_capture(const char *wire)
{
    /* Capturing a bounded string/context performs no FIFA calls. The APT
     * caller may differ from the competition owner; e-mail insertion still
     * runs exclusively through drain_bank_mail's verified owner-thread gate. */
    CareerContextRead captured;uintptr_t context;unsigned club;int date;
    char path[MAX_PATH],temp[MAX_PATH],prefix[96];FILE *file;size_t n;
    if(!bank_input_page() || !bank_mail_string(wire,512))return 0;
    n=strlen(wire);
    if(n<40 || n>=512 || strspn(wire,"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_|:-")!=n
        || (strncmp(wire,"S16BANK_V3|",11) && strncmp(wire,"S16BANK_V4|",11))
        || n<12 || strcmp(wire+n-12,"|END_S16BANK"))return 0;
    if(!bank_input_context(&captured,&context,&club,&date))return 0;
    snprintf(prefix,sizeof(prefix),"S16BANK_V%c|B57_%lu_%u_",wire[9],GetCurrentProcessId(),club);
    if(strncmp(wire,prefix,strlen(prefix)))return 0;
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\bank\\runtime\\native_request.tsv",g_mod_dir);
    snprintf(temp,sizeof(temp),"%s.new",path);file=fopen(temp,"wb");if(!file)return 0;
    fprintf(file,"schema=1\npid=%lu\nclub=%u\ncontext=%llx\nepoch=%u\ndate=%d\ncaptured_tick=%llu\nwire=%s\n",
        GetCurrentProcessId(),club,(unsigned long long)context,captured.epoch,date,(unsigned long long)GetTickCount64(),wire);
    fclose(file);
    if(!MoveFileExA(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return 0;
    /* A first installation may create runtime directories after the loader
     * hook. Republish availability with a captured click as well. */
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\bank\\runtime\\native_input_ready.tsv",g_mod_dir);
    snprintf(temp,sizeof(temp),"%s.new",path);file=fopen(temp,"wb");
    if(file){fprintf(file,"schema=1\npid=%lu\nready=1\n",GetCurrentProcessId());fclose(file);MoveFileExA(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);}
    append_loader_log("career_bank_request_captured_directly");return 1;
}

#include "manager_profile_wire.h"
#include "manager_settings_wire.h"
#include "manager_history_wire.h"
static int manager_market_capture(const char *wire,int mode)
{
    static const unsigned offsets[]={232,192,136,472};
    uintptr_t node=0,context;char page[96],path[MAX_PATH],temp[MAX_PATH];unsigned i,club;int date;
    CareerContextRead captured;FILE *file;FILETIME created,exit,kernel,user;ULARGE_INTEGER identity;
    if(!bank_mail_string(wire,512)||!(mode==2?manager_history_wire_valid(wire):mode==1?manager_settings_wire_valid(wire):manager_profile_wire_valid(wire)))return 0;
    if(!read_card_scope((uintptr_t)g_module_base+0x3809030,&node,8))return 0;
    for(i=0;i<4;++i)if(!node||!read_card_scope(node+offsets[i],&node,8))return 0;
    if(!node||!read_card_scope(node,page,sizeof(page))||!memchr(page,0,sizeof(page))
        ||strcmp(page,"game/screens/career/server16/ManagerMarket"))return 0;
    if(!bank_input_context(&captured,&context,&club,&date)
        ||!GetProcessTimes(GetCurrentProcess(),&created,&exit,&kernel,&user))return 0;
    identity.LowPart=created.dwLowDateTime;identity.HighPart=created.dwHighDateTime;
    snprintf(path,sizeof(path),"%s\\runtime\\manager_market\\%s_request.tsv",g_mod_dir,mode==2?"history":mode==1?"settings":"profile");
    snprintf(temp,sizeof(temp),"%s.new",path);file=fopen(temp,"wb");if(!file)return 0;
    fprintf(file,"schema=1\npid=%lu\ncreated=%llu\nclub=%u\ncontext=%llx\nepoch=%u\ndate=%d\ncaptured_tick=%llu\nwire=%s\n",
        GetCurrentProcessId(),(unsigned long long)identity.QuadPart,club,(unsigned long long)context,captured.epoch,date,(unsigned long long)GetTickCount64(),wire);
    fclose(file);return MoveFileExA(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)!=0;
}

static void competition_back_request(void);
static int frontend_ui_is_owner(void);
static uintptr_t background_menu_view(void);
static void drain_frontend_ui_tick(void);
static void drain_background_refresh(void);
static uintptr_t bank_input_event(void *bridge,const char *controller,const char *event,const char *argument)
{
    typedef uintptr_t (*Dispatch)(void *,const char *,const char *,const char *);
    if(bank_mail_string(event,128)&&!strcmp(event,"Server16FrontendTick")){
        if(bank_mail_string(controller,64)&&!strcmp(controller,"Calendar")
            &&bank_mail_string(argument,16)&&!strcmp(argument,"tick")
            &&frontend_ui_is_owner()&&background_menu_view()){
            drain_frontend_ui_tick();drain_background_refresh();
        }
        return 0;
    }
    if(bank_mail_string(event,128)&&(!strcmp(event,"Server16ManagerProfile")||!strcmp(event,"Server16ManagerSettings")||!strcmp(event,"Server16ClubHistory"))) {
        if(bank_mail_string(controller,64)&&!strcmp(controller,"Calendar"))(void)manager_market_capture(argument,!strcmp(event,"Server16ClubHistory")?2:!strcmp(event,"Server16ManagerSettings"));
        return 0;
    }
    if(bank_mail_string(event,128) && !strcmp(event,"Server16RoomScene")) {
        if(bank_mail_string(controller,64) && !strcmp(controller,"Calendar")
            && bank_mail_string(argument,192)) {
            typedef BOOL (WINAPI *RoomCommand)(const char *);
            HMODULE module=GetModuleHandleW(L"native_dressing_room.dll");
            RoomCommand capture=module?(RoomCommand)GetProcAddress(module,"Fifa16RoomSceneCommand"):NULL;
            if(capture)(void)capture(argument);
        }
        return 0;
    }
    if(bank_mail_string(event,128) && !strcmp(event,"Server16ClubBrowser")) {
        if(bank_mail_string(controller,64) && !strcmp(controller,"Calendar") && bank_mail_string(argument,32)) {
            typedef BOOL (WINAPI *ClubCommand)(const char *);
            HMODULE module=GetModuleHandleW(L"club_browser.dll");
            ClubCommand command=module?(ClubCommand)GetProcAddress(module,"Fifa16ClubBrowserCommand"):NULL;
            if(!strcmp(argument,"comp_back")) {
                typedef int (WINAPI *CompetitionBack)(void);
                CompetitionBack back=module?(CompetitionBack)GetProcAddress(module,"Fifa16ClubBrowserCompetitionBack"):NULL;
                if(back && back()==0)competition_back_request();
                return 0;
            }
            if(command)(void)command(argument);
        }
        return 0;
    }
    if(bank_mail_string(event,128) && !strcmp(event,"Server16SubmitBank")) {
        if(bank_mail_string(controller,64) && !strcmp(controller,"Calendar"))
            (void)bank_input_capture(argument);
        return 0;
    }
    return ((Dispatch)(*(void ***)bridge)[5])(bridge,controller,event,argument);
}

static int install_bank_input_hook(FILE *log)
{
    /* mov rax,[rcx]; call [rax+28] occupies six complete instructions bytes.
     * Replace only this ION_CareerMode.SendSystemEvent call site, not a shared
     * vtable or function entry. The following instruction is untouched. */
    static const unsigned char expected[]={0x48,0x8b,0x01,0xff,0x50,0x28};
    unsigned char *site=g_module_base+0x4502de2,*relay;
    unsigned char patch[6]={0xe8,0,0,0,0,0x90};uintptr_t target=(uintptr_t)bank_input_event;
    intptr_t delta;int32_t relative;DWORD old,ignored;char path[MAX_PATH],temp[MAX_PATH];FILE *file;
    if(memcmp(site,expected,sizeof(expected)))return 0;
    relay=career_allocate_relay_page((uintptr_t)g_module_base);if(!relay)return 0;
    delta=relay-(site+5);
    if(delta<INT32_MIN || delta>INT32_MAX){VirtualFree(relay,0,MEM_RELEASE);return 0;}
    relay[0]=0x48;relay[1]=0xb8;memcpy(relay+2,&target,8);relay[10]=0xff;relay[11]=0xe0;
    relative=(int32_t)delta;memcpy(patch+1,&relative,4);
    if(!VirtualProtect(site,sizeof(patch),PAGE_EXECUTE_READWRITE,&old)){VirtualFree(relay,0,MEM_RELEASE);return 0;}
    memcpy(site,patch,sizeof(patch));FlushInstructionCache(GetCurrentProcess(),relay,12);
    FlushInstructionCache(GetCurrentProcess(),site,sizeof(patch));VirtualProtect(site,sizeof(patch),old,&ignored);
    if(log)fprintf(log,"[OK BANK INPUT] ION SendSystemEvent capture @ %p\n",site);
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\bank\\runtime\\native_input_ready.tsv",g_mod_dir);
    snprintf(temp,sizeof(temp),"%s.new",path);file=fopen(temp,"wb");
    if(file){fprintf(file,"schema=1\npid=%lu\nready=1\n",GetCurrentProcessId());fclose(file);MoveFileExA(temp,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);}
    return 1;
}
