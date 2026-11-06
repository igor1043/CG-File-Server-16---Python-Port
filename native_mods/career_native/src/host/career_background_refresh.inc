/* The background plugin may request work from GameFlow::Render, but must
 * never enter the native UI/string allocator there. Drain on the genuine
 * StatisticsData owner thread, after the card publication has returned. */
typedef struct CareerBackgroundRefresh {
    void *owner;
    void *vtable;
    void *registry;
    uintptr_t view;
    unsigned long context;
    int room,frontend;
    ULONGLONG entered_at,deadline;
} CareerBackgroundRefresh;
static SRWLOCK g_background_refresh_lock = SRWLOCK_INIT;
static CareerBackgroundRefresh g_background_refresh;

static int background_refresh_loader_idle(void)
{
    uintptr_t service=0,commands=0,items=0;unsigned i;
    if(!read_card_scope((uintptr_t)g_module_base+0x34ea0e8,&service,sizeof(service))||!service
        ||!read_card_scope(service+0x68,&commands,sizeof(commands))||!commands
        ||!read_card_scope(commands,&items,sizeof(items))||!items)return 0;
    for(i=0;i<3;++i) {
        uintptr_t object=0,vtable=0,method=0;int state=-1;
        if(read_card_scope(items+i*8,&object,sizeof(object))&&object
            &&read_card_scope(object,&vtable,sizeof(vtable))&&vtable
            &&read_card_scope(vtable+8,&method,sizeof(method))
            &&method==(uintptr_t)g_module_base+0x3d8e370
            &&read_card_scope(object+0x30,&state,sizeof(state)))return state==0||state==12;
    }
    return 0;
}

static uintptr_t background_room_view(void)
{
    static const unsigned offsets[]={232,192,136};
    uintptr_t node=0,page=0,check=0;char name[128];size_t i;
    if (!read_card_scope((uintptr_t)g_module_base+0x3809030,&node,sizeof(node))) return 0;
    for (i=0;i<3;++i) if (!node || !read_card_scope(node+offsets[i],&node,sizeof(node))) return 0;
    return node && read_card_scope(node+472,&page,sizeof(page)) && page
        && read_card_scope(page,name,sizeof(name)) && memchr(name,0,sizeof(name))
        && !strcmp(name,"game/screens/career/server16/DressingRoom")
        && read_card_scope(node+472,&check,sizeof(check)) && check==page?node:0;
}

static uintptr_t background_menu_view(void)
{
    static const unsigned offsets[]={232,192,136};
    uintptr_t node=0,page=0,check=0;char name[128];size_t i;
    if(!read_card_scope((uintptr_t)g_module_base+0x3809030,&node,sizeof(node)))return 0;
    for(i=0;i<3;++i)if(!node||!read_card_scope(node+offsets[i],&node,sizeof(node)))return 0;
    if(!node||!read_card_scope(node+472,&page,sizeof(page))||!page
        ||!read_card_scope(page,name,sizeof(name))||!memchr(name,0,sizeof(name))
        ||!read_card_scope(node+472,&check,sizeof(check))||check!=page)return 0;
    {const char *leaf=strrchr(name,'/');leaf=leaf?leaf+1:name;
        return !_stricmp(leaf,"MainMenuWithStadium")||!_stricmp(leaf,"MainMenuHub")
            ||!_stricmp(leaf,"FluxHub")?node:0;}
}

static int background_refresh_owner_valid(void *owner, void *vtable, void *registry)
{
    uintptr_t actual_vtable = 0, actual_registry = 0, factory = 0;
    return read_card_scope((uintptr_t)owner, &actual_vtable, sizeof(actual_vtable))
        && actual_vtable == (uintptr_t)vtable
        && read_card_scope((uintptr_t)owner + 8, &actual_registry, sizeof(actual_registry))
        && actual_registry && (!registry || actual_registry == (uintptr_t)registry)
        && read_card_scope(actual_vtable + 0x38, &factory, sizeof(factory))
        && factory == (uintptr_t)g_module_base + 0x408d1d0;
}

__declspec(dllexport) BOOL WINAPI Fifa16CareerQueueBackgroundRefresh(void *owner, void *vtable)
{
    CareerBackgroundRefresh request;
    uintptr_t registry = 0;
    memset(&request, 0, sizeof(request));
    if(frontend_ui_dispatching()){request.view=background_menu_view();request.frontend=request.view!=0;}
    if(!request.view)request.view = current_card_hub_view();
    if (!request.view) {request.view=background_room_view();request.room=request.view!=0;}
    if (!request.view || !background_refresh_owner_valid(owner, vtable, NULL)
        || !read_card_scope((uintptr_t)owner + 8, &registry, sizeof(registry))) return FALSE;
    request.owner = owner;
    request.vtable = vtable;
    request.registry = (void *)registry;
    request.context = fce_runtime_context_epoch();
    request.entered_at=GetTickCount64();request.deadline = request.entered_at + 5000;
    AcquireSRWLockExclusive(&g_background_refresh_lock);
    g_background_refresh = request;
    ReleaseSRWLockExclusive(&g_background_refresh_lock);
    return TRUE;
}

static void drain_background_refresh(void)
{
    CareerBackgroundRefresh request;
    uintptr_t view;
    AcquireSRWLockExclusive(&g_background_refresh_lock);
    request = g_background_refresh;
    if (!request.owner) {
        ReleaseSRWLockExclusive(&g_background_refresh_lock);
        return;
    }
    view = request.frontend?background_menu_view():request.room?background_room_view():current_card_hub_view();
    if (!view || view != request.view || request.context != fce_runtime_context_epoch()
        || GetTickCount64() > request.deadline) {
        memset(&g_background_refresh, 0, sizeof(g_background_refresh));
        ReleaseSRWLockExclusive(&g_background_refresh_lock);
        return;
    }
    if(request.frontend){
        if(!frontend_ui_is_owner()||g_current_stats_provider_owner||GetTickCount64()<request.entered_at+80){
            ReleaseSRWLockExclusive(&g_background_refresh_lock);return;
        }
    } else if (request.room || !g_pending_stats_provider_owner) {
        if (g_current_stats_provider_owner || !fce_runtime_is_stable()
            || Fifa16CareerContextRead.sequence&1
            || Fifa16CareerContextRead.pid!=GetCurrentProcessId()
            || Fifa16CareerContextRead.epoch!=request.context
            || Fifa16CareerContextRead.registry!=(uintptr_t)request.registry
            || Fifa16CareerContextRead.owner_thread!=GetCurrentThreadId()
            || GetTickCount64()<request.entered_at+80) {
            ReleaseSRWLockExclusive(&g_background_refresh_lock);return;
        }
    } else if (!g_pending_stats_provider_owner || g_current_stats_provider_owner
        || g_pending_stats_hub_view != view
        || g_pending_stats_context_epoch != request.context
        || GetCurrentThreadId() != g_pending_stats_thread || !fce_runtime_is_stable()
        || GetTickCount64() < g_stats_refresh_schedule.entered_at + 80) {
        ReleaseSRWLockExclusive(&g_background_refresh_lock);
        return;
    }
    /* Read again at delivery: a native background load can have begun after
     * the plugin queued this request. Do not create a second provider. */
    if(!background_refresh_loader_idle()) {
        ReleaseSRWLockExclusive(&g_background_refresh_lock);return;
    }
    memset(&g_background_refresh, 0, sizeof(g_background_refresh));
    ReleaseSRWLockExclusive(&g_background_refresh_lock);
    if (!background_refresh_owner_valid(request.owner, request.vtable, request.registry)) return;
    /* No plugin lock is held across the native event/notification dispatch. */
    ((void (*)(void *, int, void *))(g_module_base + 0x4c15b20))(request.owner, 0x9c40, NULL);
    append_loader_log("career_background_refreshed_on_ui_owner");
}
