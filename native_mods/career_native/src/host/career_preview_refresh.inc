/* A prepared package is immutable until its atomic rename. Reload only this
 * view, through the native navigation dispatcher on the captured UI owner.
 * Calendar/controller state and deferred StatisticsData owners are untouched. */
/* 1 = waiting card, 2 = populated preview. Other screens are never reloaded. */
static int preview_page_active(void)
{
    static const unsigned offsets[] = {232,192,136};
    uintptr_t node=0,page=0,check=0;
    char name[128]; size_t i;
    if (!read_card_scope((uintptr_t)g_module_base+0x3809030,&node,sizeof(node))) return 0;
    for (i=0;i<sizeof(offsets)/sizeof(offsets[0]);++i)
        if (!node || !read_card_scope(node+offsets[i],&node,sizeof(node))) return 0;
    if (!node || !read_card_scope(node+472,&page,sizeof(page)) || !page
        || !read_card_scope(page,name,sizeof(name)) || !memchr(name,0,sizeof(name))
        || !read_card_scope(node+472,&check,sizeof(check)) || check!=page) return 0;
    if (!strcmp(name,"game/screens/career/server16/MatchPreviewLoading")) return 1;
    return !strcmp(name,"game/screens/career/server16/MatchPreview")?2:0;
}

static int preview_matches_calendar(uintptr_t registry,unsigned club,int date,int fixture)
{
    FceLiveSnapshot *snapshot;const FceModel *model;const FceFixture *chosen=NULL;
    uintptr_t wrapper=0,calendar=0;int index=0,parts[3]={0},today;size_t i;
    if (memcmp(g_module_base+0x44563f0+7,"\xc7\x01",2)) return 0;
    memcpy(&index,g_module_base+0x44563f0+9,sizeof(index));
    if (index<0 || index>255
        || !read_card_scope(registry+(uintptr_t)index*32+24,&wrapper,sizeof(wrapper))
        || !read_card_scope(wrapper,&calendar,sizeof(calendar))
        || !read_card_scope(calendar+0x34,parts,sizeof(parts))) return 0;
    today=fce_date_pack(parts[0],parts[1],parts[2]);
    if (today<0 || today!=date) return 0;
    snapshot=fce_runtime_cached_acquire();model=fce_runtime_model(snapshot);
    if (model) for (i=0;i<model->fixture_count;++i) {
        const FceFixture *row=&model->fixtures[i];
        if (row->played_raw || row->date_raw<today || (row->home!=(int)club && row->away!=(int)club)) continue;
        if (!chosen || row->date_raw<chosen->date_raw
            || (row->date_raw==chosen->date_raw && (row->time_raw<chosen->time_raw
                || (row->time_raw==chosen->time_raw && row->id<chosen->id)))) chosen=row;
    }
    i=model && (chosen?chosen->id==fixture:fixture==0);
    fce_runtime_release(snapshot);return (int)i;
}

static void drain_preview_refresh(void)
{
    static ULONGLONG next;
    static char applied[65];
    char path[MAX_PATH],line[256],revision[65]={0};
    unsigned schema=0,pid=0,club=0; unsigned long long requested_context=0;
    uintptr_t service,registry,bridge=0,vtable=0,dispatch=0,contexts,context;
    int selected,page,date=0,fixture=-1; FILE *file;
    page=preview_page_active();
    if (!page) {applied[0]=0;return;}
    if (!fce_runtime_is_stable() || g_current_stats_provider_owner
        || Fifa16CareerContextRead.sequence&1
        || Fifa16CareerContextRead.pid!=GetCurrentProcessId()
        || Fifa16CareerContextRead.epoch!=fce_runtime_context_epoch()
        || Fifa16CareerContextRead.owner_thread!=GetCurrentThreadId()
        || GetTickCount64()<next) return;
    next=GetTickCount64()+500;
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\preview\\runtime\\native_refresh.tsv",g_mod_dir);
    file=fopen(path,"rb"); if (!file) return;
    while (fgets(line,sizeof(line),file)) {
        if (sscanf(line,"schema=%u",&schema)==1) continue;
        if (sscanf(line,"pid=%u",&pid)==1) continue;
        if (sscanf(line,"club=%u",&club)==1) continue;
        if (sscanf(line,"context=%llx",&requested_context)==1) continue;
        if (sscanf(line,"date=%d",&date)==1) continue;
        if (sscanf(line,"fixture=%d",&fixture)==1) continue;
        if (!strncmp(line,"revision=",9) && strcspn(line+9,"\r\n")==64
            && strspn(line+9,"0123456789abcdef")==64) memcpy(revision,line+9,64);
    }
    fclose(file);
    if (schema!=2 || pid!=GetCurrentProcessId() || !revision[0]
        || (page==2 && !strcmp(revision,applied))) return;
    service=Fifa16CareerContextRead.service;registry=Fifa16CareerContextRead.registry;
    if (!is_readable_range((void *)service,32)
        || *(uintptr_t *)service!=Fifa16CareerContextRead.vtable) return;
    selected=*(int *)(service+0x14);contexts=*(uintptr_t *)(service+0x18);
    if (selected<0 || selected>7 || !contexts) return;
    context=contexts+(uintptr_t)selected*0x318;
    if (context!=(uintptr_t)requested_context || !is_readable_range((void *)context,0x318)
        || *(unsigned *)(context+0x1a4)!=club || *(int *)(context+0x18c)!=1
        || !preview_matches_calendar(registry,club,date,fixture)) return;
    /* Mirror ION_CareerMode.SendSystemEvent's verified native bridge
     * (4502dd5 -> interface+28 -> 4047290). MainMenuHub's C++ controller
     * ignores custom NAV events; the ION bridge routes to the loaded flow. */
    if (!read_card_scope((uintptr_t)g_module_base+0x35188d0,&bridge,sizeof(bridge))
        || !read_card_scope(bridge,&vtable,sizeof(vtable))
        || vtable!=(uintptr_t)g_module_base+0x21aeb40
        || !read_card_scope(vtable+0x28,&dispatch,sizeof(dispatch))
        || dispatch!=(uintptr_t)g_module_base+0x4047290
        || memcmp(g_module_base+0x4047290,"\x48\x89\x5c\x24\x10",5)
        || !preview_page_active()) return;
    memcpy(applied,revision,sizeof(applied));
    ((void (*)(void *,const char *,const char *,const char *))dispatch)(
        (void *)bridge,"Calendar","Server16RefreshMatchPreview","");
    append_loader_log("career_preview_refreshed_on_ui_owner");
}
