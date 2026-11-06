/* Registration is called only from FIFA's Background ViewModel factory,
 * never from the render worker. The engine Update dispatches on that same
 * thread; exiting Career may invalidate CareerContext without losing this
 * independent frontend owner. No native UI is invoked at registration. */
typedef void (*FrontendUiCallback)(void);
static PVOID volatile g_frontend_ui_callback;
static volatile LONG g_frontend_ui_thread,g_frontend_ui_running;

__declspec(dllexport) BOOL WINAPI Fifa16FrontendRegisterUiCallback(FrontendUiCallback callback)
{
    PVOID previous;
    if(!callback)return FALSE;
    previous=InterlockedCompareExchangePointer(&g_frontend_ui_callback,(PVOID)callback,NULL);
    if(previous && previous!=(PVOID)callback)return FALSE;
    InterlockedExchange(&g_frontend_ui_thread,(LONG)GetCurrentThreadId());
    return TRUE;
}
static int frontend_ui_is_owner(void)
{
    return InterlockedCompareExchange(&g_frontend_ui_thread,0,0)==(LONG)GetCurrentThreadId();
}
static int frontend_ui_dispatching(void)
{
    return frontend_ui_is_owner()&&InterlockedCompareExchange(&g_frontend_ui_running,0,0)!=0;
}
static void drain_frontend_ui_tick(void)
{
    FrontendUiCallback callback;
    if(!frontend_ui_is_owner()||InterlockedCompareExchange(&g_frontend_ui_running,1,0))return;
    callback=(FrontendUiCallback)InterlockedCompareExchangePointer(&g_frontend_ui_callback,NULL,NULL);
    __try {if(callback)callback();}
    __except(EXCEPTION_EXECUTE_HANDLER){
        InterlockedCompareExchangePointer(&g_frontend_ui_callback,NULL,(PVOID)callback);
        append_loader_log("frontend_ui_callback_disabled");
    }
    InterlockedExchange(&g_frontend_ui_running,0);
}
