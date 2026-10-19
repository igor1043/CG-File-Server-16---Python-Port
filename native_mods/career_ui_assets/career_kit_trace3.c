#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <stdint.h>
#include <string.h>
#include <stdarg.h>

typedef struct { char *buffer; size_t written, capacity; BYTE truncated; } Sink;
typedef int (__cdecl *PrintCore)(void *, Sink *, const char *, va_list);
typedef struct {
    LONG ready, calls, count, error;
} ProbeStatus;
typedef struct {
    LONG sequence, thread;
    char format[96], text[192];
    uintptr_t stack[12];
} ProbeEvent;
__declspec(dllexport) volatile ProbeStatus Fifa16KitTrace3Status;
__declspec(dllexport) ProbeEvent Fifa16KitTrace3Events[512];
static PrintCore original;
static BYTE *target;
static HMODULE pinned;
static const BYTE expected[20]={0x55,0x53,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,0x48,0x8d,0xac,0x24,0x58,0xf2,0xff,0xff};

static void safe_text(char *out,size_t capacity,const char *text,size_t available)
{
    size_t n=0;
    if(text) while(n+1<capacity && n<available && text[n]) {out[n]=text[n];++n;}
    out[n]=0;
}

static int __cdecl probe_print(void *writer,Sink *sink,const char *format,va_list args)
{
    int result=original(writer,sink,format,args);
    InterlockedIncrement(&Fifa16KitTrace3Status.calls);
    __try {
        char text[192];
        safe_text(text,sizeof(text),sink->buffer,result>=0 && (size_t)result<sink->capacity?(size_t)result:sink->capacity);
        if(strstr(text,"kits/") || strstr(text,"kits\\") || strstr(format,"kits/") || !strcmp(format,"%d_%d_%d") || strstr(format,"j%d_") || strstr(format,"j%s")) {
            LONG sequence=InterlockedIncrement(&Fifa16KitTrace3Status.count);
            ProbeEvent *event=&Fifa16KitTrace3Events[(sequence-1)%512];
            event->sequence=0;event->thread=(LONG)GetCurrentThreadId();
            safe_text(event->format,sizeof(event->format),format,95);
            safe_text(event->text,sizeof(event->text),text,191);
            memset(event->stack,0,sizeof(event->stack));
            CaptureStackBackTrace(0,12,(void**)event->stack,NULL);
            MemoryBarrier();event->sequence=sequence;
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {InterlockedIncrement(&Fifa16KitTrace3Status.error);}
    return result;
}

static BOOL install(void)
{
    HANDLE snapshot,threads[256];size_t count=0,i;
    THREADENTRY32 entry={0};BOOL next,ok=TRUE;DWORD old,ignored;
    BYTE jump[20]={0xff,0x25};void *replacement=(void*)probe_print;
    BYTE *trampoline;
    target=(BYTE*)GetModuleHandleA(NULL)+0x3c9e270;
    if(memcmp(target,expected,20))return FALSE;
    trampoline=(BYTE*)VirtualAlloc(NULL,64,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
    if(!trampoline)return FALSE;
    memcpy(trampoline,expected,20);trampoline[20]=0xff;trampoline[21]=0x25;
    memset(trampoline+22,0,4);{void *resume=target+20;memcpy(trampoline+26,&resume,8);}
    if(!VirtualProtect(trampoline,64,PAGE_EXECUTE_READ,&old))return FALSE;
    FlushInstructionCache(GetCurrentProcess(),trampoline,64);original=(PrintCore)trampoline;
    memset(jump+2,0,4);memcpy(jump+6,&replacement,8);memset(jump+14,0x90,6);
    snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);
    if(snapshot==INVALID_HANDLE_VALUE)return FALSE;
    entry.dwSize=sizeof(entry);next=Thread32First(snapshot,&entry);
    while(next) {
        if(entry.th32OwnerProcessID==GetCurrentProcessId() && entry.th32ThreadID!=GetCurrentThreadId()) {
            HANDLE thread;CONTEXT context={0};
            if(count==256){ok=FALSE;break;}
            thread=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT,FALSE,entry.th32ThreadID);
            if(!thread){ok=FALSE;break;}
            if(SuspendThread(thread)==(DWORD)-1){CloseHandle(thread);ok=FALSE;break;}
            threads[count++]=thread;context.ContextFlags=CONTEXT_CONTROL;
            if(!GetThreadContext(thread,&context) || (context.Rip>=(uintptr_t)target && context.Rip<(uintptr_t)target+20)){ok=FALSE;break;}
        }
        next=Thread32Next(snapshot,&entry);
    }
    CloseHandle(snapshot);
    if(ok && memcmp(target,expected,20))ok=FALSE;
    if(ok && !VirtualProtect(target,20,PAGE_EXECUTE_READWRITE,&old))ok=FALSE;
    if(ok){memcpy(target,jump,20);FlushInstructionCache(GetCurrentProcess(),target,20);VirtualProtect(target,20,old,&ignored);}
    for(i=count;i>0;--i){ResumeThread(threads[i-1]);CloseHandle(threads[i-1]);}
    return ok;
}

__declspec(dllexport) DWORD WINAPI Fifa16KitTrace3Start(void *unused)
{
    BYTE *exe=(BYTE*)GetModuleHandleA(NULL);IMAGE_DOS_HEADER *dos=(IMAGE_DOS_HEADER*)exe;
    IMAGE_NT_HEADERS64 *nt=(IMAGE_NT_HEADERS64*)(exe+dos->e_lfanew);
    (void)unused;
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE || nt->Signature!=IMAGE_NT_SIGNATURE || nt->FileHeader.TimeDateStamp!=0x577de45c)return 1;
    if(Fifa16KitTrace3Status.ready)return 0;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,(LPCSTR)&Fifa16KitTrace3Status,&pinned);
    if(!install())return 2;
    Fifa16KitTrace3Status.ready=1;return 0;
}
__declspec(dllexport) DWORD WINAPI Fifa16KitTrace3Stop(void *unused)
{
    HANDLE snapshot,threads[256];size_t count=0,i;THREADENTRY32 entry={0};BOOL next,ok=TRUE;DWORD old=0,ignored;void *active=NULL;
    (void)unused;memcpy(&active,target+6,8);
    if(!Fifa16KitTrace3Status.ready || target[0]!=0xff || target[1]!=0x25 || active!=(void*)probe_print)return 1;
    snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0);if(snapshot==INVALID_HANDLE_VALUE)return 2;
    entry.dwSize=sizeof(entry);next=Thread32First(snapshot,&entry);
    while(next){
        if(entry.th32OwnerProcessID==GetCurrentProcessId() && entry.th32ThreadID!=GetCurrentThreadId()){
            HANDLE thread;CONTEXT context={0};if(count==256){ok=FALSE;break;}
            thread=OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT,FALSE,entry.th32ThreadID);if(!thread){ok=FALSE;break;}
            if(SuspendThread(thread)==(DWORD)-1){CloseHandle(thread);ok=FALSE;break;}threads[count++]=thread;context.ContextFlags=CONTEXT_CONTROL;
            if(!GetThreadContext(thread,&context) || (context.Rip>=(uintptr_t)target && context.Rip<(uintptr_t)target+20)){ok=FALSE;break;}
        }
        next=Thread32Next(snapshot,&entry);
    }
    CloseHandle(snapshot);
    if(ok && !VirtualProtect(target,20,PAGE_EXECUTE_READWRITE,&old))ok=FALSE;
    if(ok){memcpy(target,expected,20);FlushInstructionCache(GetCurrentProcess(),target,20);VirtualProtect(target,20,old,&ignored);Fifa16KitTrace3Status.ready=0;}
    for(i=count;i>0;--i){ResumeThread(threads[i-1]);CloseHandle(threads[i-1]);}
    return ok?0:3;
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved)
{
    (void)reserved;if(reason==DLL_PROCESS_ATTACH)DisableThreadLibraryCalls(instance);return TRUE;
}
