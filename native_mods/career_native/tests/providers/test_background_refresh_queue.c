#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char *g_module_base;
static void *g_pending_stats_provider_owner, *g_current_stats_provider_owner;
static uintptr_t g_pending_stats_hub_view, active_view = 0x1234;
static unsigned long g_pending_stats_context_epoch, context = 7;
static DWORD g_pending_stats_thread, native_thread;
static struct { ULONGLONG entered_at; } g_stats_refresh_schedule;
static int stable = 1, calls, logs;
static struct {unsigned sequence,pid,epoch,owner_thread;uintptr_t registry;} Fifa16CareerContextRead;
static int read_card_scope(uintptr_t address, void *output, size_t size)
{
    SIZE_T received = 0;
    return ReadProcessMemory(GetCurrentProcess(), (const void *)address, output, size, &received)
        && received == size;
}
static uintptr_t current_card_hub_view(void) { return active_view; }
static unsigned long fce_runtime_context_epoch(void) { return context; }
static int fce_runtime_is_stable(void) { return stable; }
static void append_loader_log(const char *message) { (void)message; ++logs; }
#include "../../src/host/frontend_ui_owner.inc"
#include "../../src/host/career_background_refresh.inc"
static void native_refresh(void *owner, int command, void *data)
{
    assert(owner && command == 0x9c40 && !data);
    native_thread = GetCurrentThreadId();
    ++calls;
}
static void menu_callback(void) {}
static void *owner[2];
static uintptr_t vtable[10];
static unsigned char stadium_service[0x80],stadium_object[0x40];
static uintptr_t stadium_commands,stadium_items[3],stadium_vtable[2];
static DWORD WINAPI render_request(void *unused)
{
    (void)unused;
    assert(Fifa16CareerQueueBackgroundRefresh(owner, vtable));
    assert(Fifa16CareerQueueBackgroundRefresh(owner, vtable));
    drain_background_refresh();
    return 0;
}
int main(void)
{
    unsigned char jump[] = {0x48,0xb8,0,0,0,0,0,0,0,0,0xff,0xe0};
    uintptr_t target = (uintptr_t)native_refresh;
    HANDLE render;
    g_module_base = VirtualAlloc(NULL, 0x4c16000, MEM_RESERVE, PAGE_NOACCESS);
    assert(g_module_base);
    assert(VirtualAlloc(g_module_base+0x34ea000,4096,MEM_COMMIT,PAGE_READWRITE));
    *(void **)(g_module_base+0x34ea0e8)=stadium_service;
    *(void **)(stadium_service+0x68)=&stadium_commands;
    stadium_commands=(uintptr_t)stadium_items;stadium_items[0]=(uintptr_t)stadium_object;
    *(void **)stadium_object=stadium_vtable;stadium_vtable[1]=(uintptr_t)g_module_base+0x3d8e370;
    assert(VirtualAlloc(g_module_base + 0x4c15000, 4096, MEM_COMMIT, PAGE_EXECUTE_READWRITE));
    memcpy(jump + 2, &target, sizeof(target));
    memcpy(g_module_base + 0x4c15b20, jump, sizeof(jump));
    FlushInstructionCache(GetCurrentProcess(), g_module_base + 0x4c15b20, sizeof(jump));
    vtable[7] = (uintptr_t)g_module_base + 0x408d1d0;
    owner[0] = vtable; owner[1] = &logs;
    g_pending_stats_provider_owner = &context;
    g_pending_stats_hub_view = active_view;
    g_pending_stats_context_epoch = context;
    g_pending_stats_thread = GetCurrentThreadId();
    g_stats_refresh_schedule.entered_at = GetTickCount64() - 1000;
    render = CreateThread(NULL, 0, render_request, NULL, 0, NULL);
    assert(render && WaitForSingleObject(render, 5000) == WAIT_OBJECT_0);
    CloseHandle(render);
    assert(calls == 0); /* Producer and a wrong-thread drain never enter FIFA. */
    stable = 0; drain_background_refresh(); assert(!calls);
    stable = 1; g_current_stats_provider_owner = owner;
    drain_background_refresh(); assert(!calls);
    g_current_stats_provider_owner = NULL;
    *(int *)(stadium_object+0x30)=14;drain_background_refresh();assert(!calls&&g_background_refresh.owner);
    *(int *)(stadium_object+0x30)=0;
    drain_background_refresh(); assert(calls == 1 && native_thread == GetCurrentThreadId());
    drain_background_refresh(); assert(calls == 1); /* Coalesced, consumed once. */

    assert(Fifa16CareerQueueBackgroundRefresh(owner, vtable));
    active_view = 0; drain_background_refresh(); /* Results/save/transition. */
    active_view = g_pending_stats_hub_view; drain_background_refresh();
    assert(calls == 1 && !g_background_refresh.owner);
    assert(Fifa16CareerQueueBackgroundRefresh(owner, vtable));
    ++active_view; drain_background_refresh();
    assert(calls == 1 && !g_background_refresh.owner);
    active_view = g_pending_stats_hub_view;
    assert(Fifa16CareerQueueBackgroundRefresh(owner, vtable));
    ++context; drain_background_refresh();
    assert(calls == 1 && !g_background_refresh.owner); --context;
    assert(Fifa16CareerQueueBackgroundRefresh(owner, vtable));
    owner[1] = &context; drain_background_refresh();
    assert(calls == 1 && !g_background_refresh.owner); owner[1] = &logs;
    assert(Fifa16CareerQueueBackgroundRefresh(owner, vtable));
    g_background_refresh.deadline = GetTickCount64() - 1; drain_background_refresh();
    assert(calls == 1 && !g_background_refresh.owner);
    vtable[7] = 0; assert(!Fifa16CareerQueueBackgroundRefresh(owner, vtable));
    assert(!Fifa16CareerQueueBackgroundRefresh((void *)1, vtable));
    /* Room entry uses its exact view lifetime and published UI owner,
     * independently of the temporary Hub StatisticsData object. */
    {
        unsigned char nodes[0x1500]={0};
        assert(VirtualAlloc(g_module_base+0x3809000,4096,MEM_COMMIT,PAGE_READWRITE));
        *(void **)(g_module_base+0x3809030)=nodes;
        *(void **)(nodes+232)=nodes+0x400;*(void **)(nodes+0x400+192)=nodes+0x800;
        *(void **)(nodes+0x800+136)=nodes+0xc00;*(void **)(nodes+0xc00+472)=nodes+0x1000;
        strcpy_s((char *)nodes+0x1000,128,"game/screens/career/server16/DressingRoom");
        active_view=0;g_pending_stats_provider_owner=NULL;vtable[7]=(uintptr_t)g_module_base+0x408d1d0;
        Fifa16CareerContextRead.pid=GetCurrentProcessId();Fifa16CareerContextRead.epoch=context;
        Fifa16CareerContextRead.registry=(uintptr_t)owner[1];Fifa16CareerContextRead.owner_thread=GetCurrentThreadId();
        assert(Fifa16CareerQueueBackgroundRefresh(owner,vtable));
        drain_background_refresh();assert(calls==1);
        g_background_refresh.entered_at=GetTickCount64()-100;
        Fifa16CareerContextRead.owner_thread=0;drain_background_refresh();assert(calls==1);
        Fifa16CareerContextRead.owner_thread=GetCurrentThreadId();drain_background_refresh();assert(calls==2);
        assert(Fifa16CareerQueueBackgroundRefresh(owner,vtable));
        strcpy_s((char *)nodes+0x1000,128,"game/screens/career/MailBox");drain_background_refresh();assert(calls==2&&!g_background_refresh.owner);
        /* Returning to the Hub must refresh the cover even after card jobs
         * have released their temporary StatisticsData owner. */
        active_view=0x4444;
        assert(Fifa16CareerQueueBackgroundRefresh(owner,vtable));
        g_background_refresh.entered_at=GetTickCount64()-100;
        Fifa16CareerContextRead.owner_thread=0;drain_background_refresh();assert(calls==2);
        Fifa16CareerContextRead.owner_thread=GetCurrentThreadId();
        g_current_stats_provider_owner=owner;drain_background_refresh();assert(calls==2);
        g_current_stats_provider_owner=NULL;drain_background_refresh();assert(calls==3);
        drain_background_refresh();assert(calls==3);
    }
    {
        unsigned char nodes[0x1500]={0};
        *(void **)(g_module_base+0x3809030)=nodes;
        *(void **)(nodes+232)=nodes+0x400;*(void **)(nodes+0x400+192)=nodes+0x800;
        *(void **)(nodes+0x800+136)=nodes+0xc00;*(void **)(nodes+0xc00+472)=nodes+0x1000;
        strcpy_s((char *)nodes+0x1000,128,"game/screens/frontEnd/MainMenuWithStadium");
        active_view=0;stable=0;Fifa16CareerContextRead.owner_thread=0;
        assert(Fifa16FrontendRegisterUiCallback(menu_callback));
        /* Only a real frontend dispatch may produce a main-menu request. */
        assert(!Fifa16CareerQueueBackgroundRefresh(owner,vtable));
        g_frontend_ui_running=1;assert(Fifa16CareerQueueBackgroundRefresh(owner,vtable));g_frontend_ui_running=0;
        assert(g_background_refresh.frontend);g_background_refresh.entered_at=GetTickCount64()-100;
        drain_background_refresh();assert(calls==4);
        g_frontend_ui_running=1;assert(Fifa16CareerQueueBackgroundRefresh(owner,vtable));g_frontend_ui_running=0;
        strcpy_s((char *)nodes+0x1000,128,"game/screens/online/OnlineHub");drain_background_refresh();assert(calls==4&&!g_background_refresh.owner);
        drain_frontend_ui_tick();
    }
    assert(VirtualFree(g_module_base, 0, MEM_RELEASE));
    puts("PASS: render producer never invokes native UI; owner-thread delivery, coalescing, lifecycle/context/registry/expiry guards");
    return 0;
}
