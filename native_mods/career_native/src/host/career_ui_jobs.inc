/* Optional career commands run after the existing owner-thread UI pump.
 * Registration never invokes FIFA from the registering worker thread. */
typedef void (*CareerJobUiCallback)(void);
static PVOID volatile g_career_job_ui_callback;
static PVOID volatile g_stadium_ui_callback;
static volatile LONG g_stadium_ui_running;

__declspec(dllexport) BOOL Fifa16CareerRegisterStadiumUiCallback(CareerJobUiCallback callback)
{
    PVOID previous;
    if(!callback)return FALSE;
    previous=InterlockedCompareExchangePointer(&g_stadium_ui_callback,(PVOID)callback,NULL);
    return !previous || previous==(PVOID)callback;
}

__declspec(dllexport) BOOL Fifa16CareerRegisterJobUiCallback(CareerJobUiCallback callback)
{
    PVOID previous;
    if(!callback)return FALSE;
    previous=InterlockedCompareExchangePointer(&g_career_job_ui_callback,(PVOID)callback,NULL);
    return !previous || previous==(PVOID)callback;
}

static void career_ui_jobs_tick(void)
{
    CareerJobUiCallback callback;
    drain_pending_stats_refresh();
    drain_manager_calendar();
    /* The menu has no CareerContext publication. Its callback was registered
     * by the actual Background ViewModel factory on the same native thread. */
    drain_frontend_ui_tick();
    if(frontend_ui_is_owner())drain_background_refresh();
    if(!fce_runtime_is_stable())return;
    drain_background_refresh();
    drain_bank_mail();
    drain_market_read();
    drain_manager_read();
    drain_prepared_views();
    drain_retirement_live();
    callback=(CareerJobUiCallback)InterlockedCompareExchangePointer(&g_career_job_ui_callback,NULL,NULL);
    __try {if(callback)callback();}
    __except(EXCEPTION_EXECUTE_HANDLER) {
        InterlockedCompareExchangePointer(&g_career_job_ui_callback,NULL,(PVOID)callback);
        append_loader_log("career_job_ui_callback_disabled");
    }
    /* Stadium command 0x18 allocates native UI strings. Never execute it
     * from GameFlow::Render; run last, after all readers, on the verified
     * current context owner. A save reload invalidates this publication. */
    if(Fifa16CareerContextRead.sequence&1
        || Fifa16CareerContextRead.pid!=GetCurrentProcessId()
        || Fifa16CareerContextRead.epoch!=fce_runtime_context_epoch()
        || Fifa16CareerContextRead.owner_thread!=GetCurrentThreadId())return;
    callback=(CareerJobUiCallback)InterlockedCompareExchangePointer(&g_stadium_ui_callback,NULL,NULL);
    if(!callback||InterlockedCompareExchange(&g_stadium_ui_running,1,0))return;
    __try {if(callback)callback();}
    __except(EXCEPTION_EXECUTE_HANDLER) {
        InterlockedCompareExchangePointer(&g_stadium_ui_callback,NULL,(PVOID)callback);
        append_loader_log("stadium_ui_callback_disabled");
    }
    InterlockedExchange(&g_stadium_ui_running,0);
}
