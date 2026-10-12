/* Preserve the game's formatter/allocator and resolve only UI artwork names. */
typedef int (__cdecl *UiPrintCore)(void*,void*,const char*,va_list);
typedef void (__cdecl *UiStringCore)(void*,const char*,va_list);
static UiPrintCore native_print_core;
static UiStringCore native_string_core;
static BYTE *ui_exe;
static volatile LONG redirects;
static void trace_redirect(const char *before,const char *after) {
    FILE *file;if(InterlockedIncrement(&redirects)>256)return;
    file=fopen(log_path,"ab");if(file){fprintf(file,"RESOLVE %s -> %s\r\n",before,after);fclose(file);}
}
static BOOL normalize_output(char *buffer,size_t capacity) {
    char original[MAX_PATH],replacement[MAX_PATH];size_t length;
    if(!buffer || !capacity || !InterlockedCompareExchange(&catalog_ready,0,0))return FALSE;
    length=strnlen(buffer,capacity);if(length>=sizeof(original) || length>=capacity)return FALSE;
    memcpy(original,buffer,length+1);
    if(resolve_image_path(original,replacement,sizeof(replacement)) && strlen(replacement)<capacity){strcpy(buffer,replacement);trace_redirect(original,buffer);return TRUE;}
    return FALSE;
}
static int __cdecl ui_print(char *buffer,size_t capacity,const char *format,...) {
    /* The native writer reads a truncation flag at +0x18 before writing.
       Match all four fields; leaving that byte outside the sink lets stack
       contents suppress ordinary formatting, including locale DB names. */
    struct {char *buffer;size_t written;size_t capacity;BYTE truncated;} sink={buffer,0,buffer?capacity:0,0};
    va_list arguments;int result;
    va_start(arguments,format);result=native_print_core(ui_exe+0x3c9a720,&sink,format,arguments);va_end(arguments);
    if(buffer && result>=0) {
        if((size_t)result<capacity) {
            buffer[result]=0;
            if(normalize_output(buffer,capacity))result=(int)strlen(buffer);
        } else if(capacity)buffer[capacity-1]=0;
    }
    return result;
}
static void *__cdecl ui_string(void *object,const char *format,...) {
    char **parts=(char**)object;va_list arguments;char replacement[MAX_PATH],original[MAX_PATH];size_t length;
    parts[1]=parts[0];
    va_start(arguments,format);native_string_core(object,format,arguments);va_end(arguments);
    length=(size_t)((uintptr_t)parts[1]-(uintptr_t)parts[0]);
    if(InterlockedCompareExchange(&catalog_ready,0,0) && parts[0] && length<sizeof(original)) {
        memcpy(original,parts[0],length);original[length]=0;
        if(resolve_image_path(original,replacement,sizeof(replacement))) {
            const char *argument=replacement;
            parts[1]=parts[0];native_string_core(object,"%s",(va_list)&argument);
            trace_redirect(original,replacement);
        }
    }
    return object;
}
#ifndef UI_ASSETS_TEST
typedef struct {BYTE *target;BYTE before[16];BYTE after[16];DWORD protect;} UiHook;
static BOOL freeze_other_threads(HANDLE *handles,size_t *count,const UiHook *hooks,size_t hook_count) {
    HANDLE snapshot;THREADENTRY32 entry={0};BOOL ok;size_t i;DWORD own=GetCurrentThreadId(),pid=GetCurrentProcessId();
    *count=0;snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);if(snapshot==INVALID_HANDLE_VALUE)return FALSE;
    entry.dwSize=sizeof(entry);ok=Thread32First(snapshot,&entry);
    while(ok) {
        if(entry.th32OwnerProcessID==pid && entry.th32ThreadID!=own) {
            CONTEXT context={0};HANDLE thread;
            if(*count>=256){CloseHandle(snapshot);return FALSE;}
            thread=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT|THREAD_QUERY_INFORMATION,FALSE,entry.th32ThreadID);
            if(!thread){CloseHandle(snapshot);return FALSE;}
            if(SuspendThread(thread)==(DWORD)-1){CloseHandle(thread);CloseHandle(snapshot);return FALSE;}
            handles[(*count)++]=thread;context.ContextFlags=CONTEXT_CONTROL;
            if(!GetThreadContext(thread,&context)){CloseHandle(snapshot);return FALSE;}
            for(i=0;i<hook_count;i++)if(context.Rip>=(uintptr_t)hooks[i].target && context.Rip<(uintptr_t)hooks[i].target+16){CloseHandle(snapshot);return FALSE;}
        }
        ok=Thread32Next(snapshot,&entry);
    }
    CloseHandle(snapshot);return TRUE;
}
static BOOL install_path_hooks(void) {
    static const BYTE expected[2][16]={
        {0x49,0x89,0xe3,0x4d,0x89,0x43,0x18,0x4d,0x89,0x4b,0x20,0x53,0x57,0x48,0x83,0xec},
        {0x48,0x89,0x54,0x24,0x10,0x4c,0x89,0x44,0x24,0x18,0x4c,0x89,0x4c,0x24,0x20,0x53}
    };
    uintptr_t rvas[2]={0x3c987e0,0x3a34200};void *replacements[2]={(void*)ui_print,(void*)ui_string};
    UiHook hooks[2];HANDLE threads[256];size_t count=0,i,protected_count=0;BOOL ok;DWORD ignored;
    ui_exe=(BYTE*)GetModuleHandleA(NULL);
    for(i=0;i<2;i++) {
        hooks[i].target=ui_exe+rvas[i];
        if(!read_memory(hooks[i].target,hooks[i].before,16) || memcmp(hooks[i].before,expected[i],16))return FALSE;
        memset(hooks[i].after,0x90,16);hooks[i].after[0]=0xff;hooks[i].after[1]=0x25;
        memset(hooks[i].after+2,0,4);memcpy(hooks[i].after+6,&replacements[i],8);
    }
    native_print_core=(UiPrintCore)(ui_exe+0x3c9e270);native_string_core=(UiStringCore)(ui_exe+0x3a338f0);
    ok=freeze_other_threads(threads,&count,hooks,2);
    if(ok) {
        for(i=0;i<2;i++)if(memcmp(hooks[i].target,hooks[i].before,16)){ok=FALSE;break;}
        if(ok)for(i=0;i<2;i++){if(!VirtualProtect(hooks[i].target,16,PAGE_EXECUTE_READWRITE,&hooks[i].protect)){ok=FALSE;break;}protected_count++;}
        if(ok)for(i=0;i<2;i++){memcpy(hooks[i].target,hooks[i].after,16);FlushInstructionCache(GetCurrentProcess(),hooks[i].target,16);}
        for(i=0;i<protected_count;i++)VirtualProtect(hooks[i].target,16,hooks[i].protect,&ignored);
    }
    for(i=count;i>0;i--){ResumeThread(threads[i-1]);CloseHandle(threads[i-1]);}
    return ok;
}
#endif
