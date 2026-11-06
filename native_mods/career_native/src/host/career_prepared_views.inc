/* Ready packages are opened only by the existing stable owner-thread pump.
 * Helpers publish files; they never invoke FIFA, reload a provider or edit DATA. */
typedef struct PreparedViewRecord {
    unsigned schema,pid,club,epoch;
    unsigned long long created,context,registry,captured;
    int date,fixture;char revision[65];
} PreparedViewRecord;
typedef struct PreparedViewState {ULONGLONG next,entered;int inside;char applied[65];} PreparedViewState;
static PreparedViewState g_prepared_views[5];
static SRWLOCK g_competition_back_lock=SRWLOCK_INIT;
static CareerContextRead g_competition_back_context;
static ULONGLONG g_competition_back_until;

static void competition_back_request(void)
{
    CareerContextRead captured;uintptr_t context;unsigned club;int date;
    if(!bank_input_context(&captured,&context,&club,&date))return;
    AcquireSRWLockExclusive(&g_competition_back_lock);
    g_competition_back_context=captured;g_competition_back_until=GetTickCount64()+2000;
    ReleaseSRWLockExclusive(&g_competition_back_lock);
}

/* SendSystemEvent is handled by Calendar::HandleSystemScreenEvent, which
 * accepts DONE_LOADING but ignores custom navigation events. Queue the same
 * native NavEventMessage used by MainMenu instead. The message bus owns and
 * releases the constructed message, and executes the flow outside this pump.
 * No Calendar/provider destruction is performed inside the owner callback. */
static int prepared_view_queue(uintptr_t registry,const char *event)
{
    uintptr_t manager,manager_vtable=0,secondary=0,bus,bus_vtable=0,submit=0;
    void *allocator,*memory,*message;
    manager=(uintptr_t)bank_mail_service(registry,0x4456990,0x20);
    if(!manager || !read_card_scope(manager,&manager_vtable,sizeof(manager_vtable))
        || manager_vtable!=(uintptr_t)g_module_base+0x21b5720
        || *(uintptr_t *)(manager_vtable+0x40)!=(uintptr_t)g_module_base+0x49fbe20
        || !read_card_scope(manager+0x18,&secondary,sizeof(secondary)))return 0;
    bus=(uintptr_t)bank_mail_service(secondary,0x44568e0,0x10);
    if(!bus || !read_card_scope(bus,&bus_vtable,sizeof(bus_vtable))
        || bus_vtable!=(uintptr_t)g_module_base+0x21b5530
        || !read_card_scope(bus_vtable+0x10,&submit,sizeof(submit))
        || submit!=(uintptr_t)g_module_base+0x4042000
        || memcmp(g_module_base+0x4467990,"\x48\x8b\x05",3)
        || memcmp(g_module_base+0x5c56b40,"\x48\x89\x74\x24\x10",5))return 0;
    allocator=((void *(*)(void))(g_module_base+0x4467990))();
    if(!is_readable_range(allocator,sizeof(uintptr_t))
        || !is_readable_range(*(void **)allocator,3*sizeof(uintptr_t)))return 0;
    memory=((void *(*)(void *,unsigned,const char *,unsigned))(*(void ***)allocator)[2])(
        allocator,0x98,(const char *)(g_module_base+0x3055600),0);
    if(!memory)return 0;
    message=((void *(*)(void *,const char *))(g_module_base+0x5c56b40))(memory,event);
    ((void (*)(void *,void *))submit)((void *)bus,message);
    return 1;
}

/* 1/2 = preview ready/waiting; 3/4 = market; 5 = room; 6 = finance; 7 = coaches. */
static int prepared_view_page(void)
{
    static const unsigned offsets[]={232,192,136,472};
    uintptr_t node=0;unsigned i;char page[128];
    if(!read_card_scope((uintptr_t)g_module_base+0x3809030,&node,sizeof(node)))return 0;
    for(i=0;i<4;++i)if(!node || !read_card_scope(node+offsets[i],&node,sizeof(node)))return 0;
    if(!node || !read_card_scope(node,page,sizeof(page)) || !memchr(page,0,sizeof(page)))return 0;
    if(!strcmp(page,"game/screens/career/server16/MatchPreview"))return 1;
    if(!strcmp(page,"game/screens/career/server16/MatchPreviewLoading"))return 2;
    if(!strcmp(page,"game/screens/career/server16/TransferMarket"))return 3;
    if(!strcmp(page,"game/screens/career/server16/DressingRoom"))return 5;
    if(!strcmp(page,"game/screens/career/server16/ClubFinance"))return 6;
    if(!strcmp(page,"game/screens/career/server16/ManagerMarket"))return 7;
    if(!strcmp(page,"game/screens/career/server16/CareerCompetitions"))return 8;
    return !strcmp(page,"game/screens/career/server16/TransferMarketLoading")?4:0;
}

static int prepared_view_read_file(const char *path,PreparedViewRecord *record)
{
    char line[256];FILE *file;unsigned lines=0;
    memset(record,0,sizeof(*record));
    file=fopen(path,"rb");if(!file)return 0;
    while(fgets(line,sizeof(line),file) && ++lines<=16){
        if(sscanf(line,"schema=%u",&record->schema)==1)continue;
        if(sscanf(line,"pid=%u",&record->pid)==1)continue;
        if(sscanf(line,"club=%u",&record->club)==1)continue;
        if(sscanf(line,"epoch=%u",&record->epoch)==1)continue;
        if(sscanf(line,"process_created_100ns=%llu",&record->created)==1)continue;
        if(sscanf(line,"context=%llx",&record->context)==1)continue;
        if(sscanf(line,"registry=%llx",&record->registry)==1)continue;
        if(sscanf(line,"captured_ms=%llu",&record->captured)==1)continue;
        if(sscanf(line,"date=%d",&record->date)==1)continue;
        if(sscanf(line,"fixture=%d",&record->fixture)==1)continue;
        if(!strncmp(line,"revision=",9) && strcspn(line+9,"\r\n")==64 && strspn(line+9,"0123456789abcdef")==64)memcpy(record->revision,line+9,64);
    }
    fclose(file);return lines<=16 && record->schema==1 && record->revision[0];
}

static int prepared_view_read(int kind,PreparedViewRecord *record)
{
    char path[MAX_PATH];
    if(kind==4)snprintf(path,sizeof(path),"%s\\runtime\\manager_market\\view_ready.tsv",g_mod_dir);
    else snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\%s\\view_ready.tsv",g_mod_dir,kind==3?"bank\\runtime":kind==2?"room\\runtime":kind?"market":"preview\\runtime");
    return prepared_view_read_file(path,record);
}

static int prepared_view_scope(const PreparedViewRecord *record,CareerContextRead *captured)
{
    uintptr_t contexts,context;unsigned char *calendar;int selected,parts[3];
    FILETIME created,exit,kernel,user;ULARGE_INTEGER identity;
    memcpy(captured,&Fifa16CareerContextRead,sizeof(*captured));
    if(captured->sequence&1 || captured->pid!=GetCurrentProcessId() || record->pid!=captured->pid
        || captured->epoch!=fce_runtime_context_epoch() || captured->epoch!=record->epoch
        || captured->owner_thread!=GetCurrentThreadId() || captured->registry!=record->registry
        || !is_readable_range((void *)captured->service,32) || *(uintptr_t *)captured->service!=captured->vtable)return 0;
    if(!GetProcessTimes(GetCurrentProcess(),&created,&exit,&kernel,&user))return 0;
    identity.LowPart=created.dwLowDateTime;identity.HighPart=created.dwHighDateTime;
    if(identity.QuadPart!=record->created)return 0;
    selected=*(int *)(captured->service+0x14);contexts=*(uintptr_t *)(captured->service+0x18);
    if(selected<0 || selected>7)return 0;context=contexts+(uintptr_t)selected*0x318;
    if(context!=(uintptr_t)record->context || !is_readable_range((void *)context,0x318)
        || *(int *)(context+0x18c)!=1 || *(unsigned *)(context+0x1a4)!=record->club)return 0;
    calendar=bank_mail_service(captured->registry,0x44563f0,0x40);if(!calendar)return 0;
    memcpy(parts,calendar+0x34,12);
    return fce_date_pack(parts[0],parts[1],parts[2])==record->date
        && Fifa16CareerContextRead.sequence==captured->sequence;
}

static int prepared_view_fixture(const PreparedViewRecord *record)
{
    FceLiveSnapshot *snapshot=fce_runtime_cached_acquire();const FceModel *model=fce_runtime_model(snapshot);
    const FceFixture *next=NULL;size_t i;int matches;
    if(model)for(i=0;i<model->fixture_count;++i){
        const FceFixture *row=&model->fixtures[i];
        if(row->played_raw || row->date_raw<record->date || (row->home!=(int)record->club && row->away!=(int)record->club))continue;
        if(!next || row->date_raw<next->date_raw || (row->date_raw==next->date_raw
            && (row->time_raw<next->time_raw || (row->time_raw==next->time_raw && row->id<next->id))))next=row;
    }
    matches=model && (next?next->id==record->fixture:record->fixture==0);
    fce_runtime_release(snapshot);return matches;
}

static void drain_prepared_views(void)
{
    int page=prepared_view_page(),kind,waiting,i;ULONGLONG now=GetTickCount64();
    PreparedViewState *state;PreparedViewRecord record;CareerContextRead captured;
    if(TryAcquireSRWLockExclusive(&g_competition_back_lock)) {
        if(g_competition_back_until) {
            CareerContextRead request=g_competition_back_context;
            if(page!=8 || now>g_competition_back_until || request.epoch!=fce_runtime_context_epoch())g_competition_back_until=0;
            else if(fce_runtime_is_stable() && !g_current_stats_provider_owner
                && Fifa16CareerContextRead.owner_thread==GetCurrentThreadId()
                && Fifa16CareerContextRead.epoch==request.epoch
                && Fifa16CareerContextRead.registry==request.registry
                && Fifa16CareerContextRead.service==request.service
                && !(Fifa16CareerContextRead.sequence&1)) {
                g_competition_back_until=0;
                if(prepared_view_queue(request.registry,"Back"))append_loader_log("career_competition_back_queued_on_ui_owner");
            }
        }
        ReleaseSRWLockExclusive(&g_competition_back_lock);
    }
    if(page==8)return;
    if(!page){for(i=0;i<5;++i)g_prepared_views[i].inside=0;return;}
    kind=page==7?4:page==6?3:page==5?2:page>2;waiting=page==2 || page==4;state=&g_prepared_views[kind];
    for(i=0;i<5;++i)if(i!=kind)g_prepared_views[i].inside=0;
    if(!state->inside){state->inside=1;state->entered=now;state->next=0;}
    if(now<state->next || !fce_runtime_is_stable() || g_current_stats_provider_owner)return;
    state->next=now+500;
    __try {
        if(!prepared_view_read(kind,&record) || !prepared_view_scope(&record,&captured)
            || now<record.captured || now-record.captured>12000
            || (waiting && record.captured<state->entered)
            || (!waiting && !strcmp(state->applied,record.revision))
            || (!kind && !prepared_view_fixture(&record)))return;
        if(prepared_view_page()!=page || Fifa16CareerContextRead.sequence!=captured.sequence
            || !prepared_view_queue(captured.registry,
                kind==4?"Server16RefreshManagerMarket":kind==3?"Server16RefreshClubFinance":kind==2?"Server16RefreshDressingRoom":kind?"Server16RefreshTransferMarket":"Server16RefreshMatchPreview"))return;
        memcpy(state->applied,record.revision,sizeof(state->applied));
        state->next=now+2000; /* Await the queued flow transition before retrying. */
        append_loader_log(kind==4?"career_manager_view_queued_on_ui_owner":kind==3?"career_finance_view_queued_on_ui_owner":kind==2?"career_room_view_queued_on_ui_owner":kind?"career_market_view_queued_on_ui_owner":"career_preview_view_queued_on_ui_owner");
    } __except(EXCEPTION_EXECUTE_HANDLER) {append_loader_log("career_prepared_view_waiting_after_scope_change");}
}
