/* Optional career commands run after the existing owner-thread UI pump.
 * Registration never invokes FIFA from the registering worker thread. */
typedef void (*CareerJobUiCallback)(void);
static PVOID volatile g_career_job_ui_callback;

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
    if(!fce_runtime_is_stable())return;
    callback=(CareerJobUiCallback)InterlockedCompareExchangePointer(&g_career_job_ui_callback,NULL,NULL);
    if(!callback)return;
    __try {callback();}
    __except(EXCEPTION_EXECUTE_HANDLER) {
        InterlockedCompareExchangePointer(&g_career_job_ui_callback,NULL,(PVOID)callback);
        append_loader_log("career_job_ui_callback_disabled");
    }
}
