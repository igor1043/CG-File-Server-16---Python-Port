#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fce_runtime.h"
#include "../platform/mod_paths.h"

struct FceLiveSnapshot { volatile LONG refs; unsigned long generation; FceModel model; };
static SRWLOCK snapshot_lock=SRWLOCK_INIT;
static SRWLOCK install_lock=SRWLOCK_INIT;
static FceLiveSnapshot *current,*calendar_current;
static unsigned char *module;
static volatile LONG generation=1, dirty=1, installed, busy, requested, settle_ticks;
static volatile LONG publication_revision;
static volatile LONG refresh_suppressed;
static volatile LONGLONG live_refresh_until;
static volatile LONGLONG live_refresh_next;
static volatile LONG live_refresh_interval=1000;
static size_t pending_fixture_count, pending_stat_count, pending_standing_count;
static int pending_date;
static LONG pending_matches;
static volatile LONG runtime_log_mode=FCE_RUNTIME_LOG_PRODUCTION;
static volatile LONG runtime_log_loaded;
static char runtime_log_dir[MAX_PATH];
/* Existing careers expose fixtures/standings before their statistics table.
 * Keep a few delayed retries queued after that transitional snapshot instead
 * of leaving the competition hub with its initial empty card payload. */
static ULONGLONG incomplete_retry_at;
static unsigned incomplete_retry_count;
static DWORD engine_thread;
static char log_path[MAX_PATH];
typedef void (*OneFn)(void *);
typedef void (*TwoFn)(void *,void *);
typedef void (*ReadyFn)(void *,unsigned char);
static OneFn original_update;
static TwoFn original_post,original_send,original_load;
static ReadyFn original_ready;
static FceRuntimeReadyCallback ready_callback;
static FceRuntimeUiTickCallback ui_tick_callback;
static FceRuntimeDateCallback date_callback;
void fce_runtime_set_date_callback(FceRuntimeDateCallback callback) { date_callback=callback; }

static int parse_log_mode(const char *dir) {
    char path[MAX_PATH], text[512];
    FILE *file;
    size_t count, i;
    if(!dir || !dir[0]) return FCE_RUNTIME_LOG_PRODUCTION;
    career_path_read(path,sizeof(path),dir,"config","career_native_mode.ini");
    file=fopen(path,"rb");
    if(!file) return FCE_RUNTIME_LOG_PRODUCTION;
    count=fread(text,1,sizeof(text)-1,file);
    fclose(file);
    text[count]='\0';
    for(i=0;i<count;++i) text[i]=(char)tolower((unsigned char)text[i]);
    if(strstr(text,"mode=trace") || strstr(text,"mode = trace"))
        return FCE_RUNTIME_LOG_TRACE;
    if(strstr(text,"mode=development") || strstr(text,"mode = development")
       || strstr(text,"mode=dev") || strstr(text,"mode = dev"))
        return FCE_RUNTIME_LOG_DEVELOPMENT;
    return FCE_RUNTIME_LOG_PRODUCTION;
}
void fce_runtime_log_dir(const char *dir) {
    career_path_logs(dir);
    snprintf(log_path,sizeof(log_path),"%s\\logs\\career_native_engine.log",dir);
    snprintf(runtime_log_dir,sizeof(runtime_log_dir),"%s",dir?dir:"");
    InterlockedExchange(&runtime_log_loaded,0);
}
int fce_runtime_log_mode(void) {
    if(InterlockedCompareExchange(&runtime_log_loaded,1,0)==0)
        InterlockedExchange(&runtime_log_mode,parse_log_mode(runtime_log_dir));
    return (int)InterlockedCompareExchange(&runtime_log_mode,0,0);
}
int fce_runtime_log_verbose(void) {
    return fce_runtime_log_mode()!=FCE_RUNTIME_LOG_PRODUCTION;
}
void fce_runtime_set_ready_callback(FceRuntimeReadyCallback callback) {
    ready_callback=callback;
}
void fce_runtime_set_ui_tick_callback(FceRuntimeUiTickCallback callback) {
    ui_tick_callback=callback;
}
unsigned long fce_runtime_context_epoch(void) {
    return (unsigned long)InterlockedCompareExchange(&generation,0,0);
}
void fce_runtime_request_refresh(void) {
    /* Explicit requests come from a real context/date transition and must
     * survive even when the UI redraw itself is suppressing provider noise. */
    InterlockedExchange(&dirty,1);
    InterlockedExchange(&requested,1);
    InterlockedExchange(&settle_ticks,0);
}
void fce_runtime_keep_fresh(unsigned window_ms,unsigned interval_ms) {
    ULONGLONG now=GetTickCount64();
    LONGLONG previous;
    if(window_ms<1000) window_ms=1000;
    if(window_ms>300000) window_ms=300000;
    if(interval_ms<250) interval_ms=250;
    if(interval_ms>5000) interval_ms=5000;
    InterlockedExchange(&live_refresh_interval,(LONG)interval_ms);
    previous=InterlockedExchange64(&live_refresh_until,(LONGLONG)(now+window_ms));
    /* Only the first provider entry requests immediately. Provider redraws
     * caused by publication merely extend the window; otherwise each redraw
     * would recursively queue another capture on the following frame. */
    if(previous<(LONGLONG)now) {
        InterlockedExchange64(&live_refresh_next,(LONGLONG)now);
        InterlockedExchange(&requested,1);
    }
}
void fce_runtime_suppress_refresh(int suppress) {
    InterlockedExchange(&refresh_suppressed,suppress?1:0);
}
static void report(const char *event,int result,const FceModel *m,ULONGLONG elapsed) {
    FILE *f;
    /* Normal snapshots are intentionally silent in production. Keep only a
     * rejected capture visible so a broken career context remains diagnosable
     * without the per-second append/open/close cost of the polling loop. */
    if(!fce_runtime_log_verbose() && strcmp(event,"snapshot_rejected")!=0 && strcmp(event,"derived_standings_rejected")!=0)
        return;
    if(!log_path[0]) return;
    f=fopen(log_path,"ab"); if(!f) return;
    fprintf(f,"event=%s result=%d generation=%ld date=%d fixtures=%llu stats=%llu standings=%llu unresolved=%llu elapsed_ms=%llu thread=%lu\n",
        event,result,generation,m?m->date:-1,m?(unsigned long long)m->fixture_count:0,
        m?(unsigned long long)m->stat_count:0,m?(unsigned long long)m->standing_count:0,
        m?(unsigned long long)m->unresolved_fixtures:0,(unsigned long long)elapsed,GetCurrentThreadId());
    fclose(f);
}
void fce_runtime_release(FceLiveSnapshot *s) {
    if(s && InterlockedDecrement(&s->refs)==0) { fce_model_free(&s->model); free(s); }
}
static void invalidate(void) {
    FceLiveSnapshot *old,*old_calendar;
    AcquireSRWLockExclusive(&snapshot_lock);
    old=current; current=NULL;old_calendar=calendar_current;calendar_current=NULL;
    InterlockedIncrement(&generation); InterlockedExchange(&dirty,1);
    InterlockedExchange(&requested,0); InterlockedExchange(&settle_ticks,0);
    pending_fixture_count=pending_stat_count=pending_standing_count=0;
    pending_date=-1; pending_matches=0;
    incomplete_retry_at=0; incomplete_retry_count=0;
    ReleaseSRWLockExclusive(&snapshot_lock);
    fce_runtime_release(old);
    fce_runtime_release(old_calendar);
}
void fce_runtime_invalidate(void) { invalidate(); }
static int copy_table(void *manager,size_t offset,FceRawTable *t) {
    unsigned char *table=*(unsigned char **)((unsigned char *)manager+offset);
    unsigned char *source; void *method; size_t size; int stride;
    if(!table) return 0;
    method=(*(void ***)table)[1];
    if((uintptr_t)method<(uintptr_t)module+0x1000 || (uintptr_t)method>=(uintptr_t)module+0x90000) return 0;
    stride=((int(*)(void *))method)(table);
    t->count=*(unsigned int *)(table+0x24);
    if(stride<16 || stride>1024 || t->count>65536) return 0;
    t->stride=(size_t)stride; size=t->count*t->stride;
    source=*(unsigned char **)(table+0x30);
    if(!source && size) return 0;
    t->bytes=malloc(size?size:1);
    if(!t->bytes) return 0;
    if(size) memcpy((void *)t->bytes,source,size);
    return 1;
}
#include "calendar_snapshot.inc"
#include "derived_standings.inc"
/* Executes on the thread which owns FCE::Update. Readers never walk the
 * process heap, saved DATA, old snapshots, or screen-local stat containers. */
static void capture(void *iface) {
    FceRawTable t[4]={{0}}; FceLiveSnapshot *next=NULL,*old;
    unsigned char *hub,*connector,*manager,*list,**first,**last;
    int date=-1,ok=0,model_result=FCE_UNKNOWN; const char *stage="interface_ready";
    DWORD exception=0; size_t i; LONG epoch; ULONGLONG start=GetTickCount64();
    if(InterlockedCompareExchange(&busy,1,0)) return;
    epoch=InterlockedCompareExchange(&generation,0,0);
    __try {
        if(!iface || *(void ***)iface!=(void **)(module+0x94360) || !*((unsigned char *)iface+0x30)) __leave;
        stage="hub";
        hub=*(unsigned char **)((unsigned char *)iface+0x18);
        if(!hub) __leave;
        stage="connector";
        connector=*(unsigned char **)(hub+0x28);
        if(!connector) __leave;
        stage="data_manager";
        manager=*(unsigned char **)(connector+0x18);
        if(!manager) __leave;
        stage="manager_list";
        list=*(unsigned char **)(hub+0x20);
        if(!list) __leave;
        first=*(unsigned char ***)(list+8); last=*(unsigned char ***)(list+0x10);
        if(last<first || (size_t)(last-first)>16) __leave;
        for(;first<last;++first) {
            if(*first && *(int *)(*first+0x20)==5) {
                date=fce_date_pack(*(int *)(*first+0x3c),*(int *)(*first+0x40),*(int *)(*first+0x44));
                break;
            }
        }
        /* Type 5 is the match simulator, not the career CalendarManager.
         * Its +0x3c fields can remain -1 throughout a loaded career. */
        if(date_callback) {
            int calendar_date=date_callback();
            if(fce_date_valid(calendar_date))date=calendar_date;
        }
        stage="copy_competitions"; if(!copy_table(manager,0x48,t)) __leave;
        stage="copy_standings"; if(!copy_table(manager,0x80,t+1)) __leave;
        stage="copy_statistics"; if(!copy_table(manager,0x88,t+2)) __leave;
        stage="copy_fixtures"; if(!copy_table(manager,0x58,t+3)) __leave;
        ok=1;
    } __except(EXCEPTION_EXECUTE_HANDLER) { ok=0; exception=GetExceptionCode(); }
    if(ok) {
        stage="allocate_snapshot";
        next=calloc(1,sizeof(*next));
        if(!next) ok=0;
        else {
            next->refs=1;
            stage="decode_model";
            model_result=fce_model_build(t,date,&next->model);
            ok=model_result==FCE_OK;
        }
    }
    for(i=0;i<4;++i) free((void *)t[i].bytes);
    if(ok) {
        /* FCE rebuilds its tables in stages after simulation: fixtures and
         * standings commonly become visible one or two updates before player
         * statistics.  Publishing that intermediate image leaves only some
         * cards populated until the screen is recreated.  Require the same
         * complete table shape on three spaced captures and keep the former
         * snapshot alive while confirmation is pending. */
        if(pending_fixture_count==next->model.fixture_count &&
           pending_stat_count==next->model.stat_count &&
           pending_standing_count==next->model.standing_count &&
           pending_date==next->model.date) {
            ++pending_matches;
        } else {
            pending_fixture_count=next->model.fixture_count;
            pending_stat_count=next->model.stat_count;
            pending_standing_count=next->model.standing_count;
            pending_date=next->model.date;
            pending_matches=1;
        }
        if(pending_matches<2) {
            report("snapshot_waiting",0,&next->model,GetTickCount64()-start);
            fce_runtime_release(next);
            InterlockedExchange(&requested,1);
            InterlockedExchange(&settle_ticks,0);
            InterlockedExchange(&busy,0);
            return;
        }
        pending_matches=0;
    }
    if(ok && epoch==InterlockedCompareExchange(&generation,0,0)) {
        /* generation is the capture epoch used to reject a stale context;
         * publication_revision identifies every stable image of that same
         * career, including unsaved calendar simulation advances. */
        next->generation=(unsigned long)InterlockedIncrement(&publication_revision);
        AcquireSRWLockExclusive(&snapshot_lock);
        old=current; current=next;
        ReleaseSRWLockExclusive(&snapshot_lock);
        fce_runtime_release(old);
        report("snapshot",1,&next->model,GetTickCount64()-start);
        /* A saved career normally has fixtures already populated while the
         * statistics provider is still rebuilding.  Retry from the FCE owner
         * thread, bounded so an untouched brand-new career (legitimately no
         * stats) never becomes a permanent polling loop. */
        if (next->model.fixture_count > 0 && next->model.stat_count == 0
            && incomplete_retry_count < 5) {
            ++incomplete_retry_count;
            incomplete_retry_at=GetTickCount64()+750;
        } else if (next->model.stat_count > 0 || !next->model.fixture_count) {
            incomplete_retry_at=0;
            incomplete_retry_count=0;
        }
        /* Snapshot publication happens on FCE's owning Update thread.  Let
         * the career UI adapter refresh a provider that was initially built
         * against generation zero, without polling the screen continuously. */
        if (ready_callback)
            ready_callback(next->generation);
    } else {
        FILE *diagnostic=log_path[0]?fopen(log_path,"ab"):NULL;
        if(diagnostic) {
            fprintf(diagnostic,"reject_detail stage=%s model_result=%d exception=0x%08lX iface=%p slots=%llu/%llu/%llu/%llu strides=%llu/%llu/%llu/%llu sim_date=%d epoch=%ld current_epoch=%ld\n",
                stage,model_result,(unsigned long)exception,iface,
                (unsigned long long)t[0].count,(unsigned long long)t[1].count,(unsigned long long)t[2].count,(unsigned long long)t[3].count,
                (unsigned long long)t[0].stride,(unsigned long long)t[1].stride,(unsigned long long)t[2].stride,(unsigned long long)t[3].stride,
                date,epoch,InterlockedCompareExchange(&generation,0,0));
            fclose(diagnostic);
        }
        fce_runtime_release(next);
        /* On a failed copy never leave the former career visible. */
        invalidate(); report("snapshot_rejected",0,NULL,GetTickCount64()-start);
    }
    InterlockedExchange(&busy,0);
}
static void update_hook(void *self) {
    ULONGLONG now;
    LONGLONG until,next;
    LONG interval;
    engine_thread=GetCurrentThreadId();
    original_update(self);
    /* Calendar evidence does not depend on the player-statistics/UI settle
     * gate. Copy only after the native Update returns, on its owning thread. */
    calendar_capture(self);
    derived_tick(self);
    now=GetTickCount64();
    until=InterlockedCompareExchange64(&live_refresh_until,0,0);
    next=InterlockedCompareExchange64(&live_refresh_next,0,0);
    interval=InterlockedCompareExchange(&live_refresh_interval,0,0);
    if(until>=(LONGLONG)now && next<=(LONGLONG)now) {
        InterlockedExchange64(&live_refresh_next,(LONGLONG)(now+(interval>0?interval:1000)));
        InterlockedExchange(&requested,1);
    }
    if (!InterlockedCompareExchange(&requested,0,0)
        && incomplete_retry_at
        && GetTickCount64() >= incomplete_retry_at) {
        incomplete_retry_at=0;
        InterlockedExchange(&requested,1);
        InterlockedExchange(&settle_ticks,0);
    }
    /* A load, simulation advance or tournament hand-off recreates the FCE
     * tables over more than one update.  Do not inspect its containers from
     * a UI-provider callback while that reconstruction is in progress. */
    if(InterlockedCompareExchange(&settle_ticks,0,0)<4) {
        InterlockedIncrement(&settle_ticks);
        if(ui_tick_callback) ui_tick_callback();
        return;
    }
    if(InterlockedExchange(&requested,0)) {
        InterlockedExchange(&dirty,0); capture(self);
    }
    if(ui_tick_callback) ui_tick_callback();
}
static void post_hook(void *self,void *request) {
    original_post(self,request);
    /* Start rebuilding before the user returns from calendar/simulation to
     * the competition hub.  Previously the first hub provider callback was
     * what started the capture, so the finished snapshot arrived too late. */
    if(!InterlockedCompareExchange(&refresh_suppressed,0,0)) {
        InterlockedExchange(&dirty,1); InterlockedExchange(&requested,1);
        InterlockedExchange(&settle_ticks,0);
    }
}
static void send_hook(void *self,void *request) {
    original_send(self,request);
    if(!InterlockedCompareExchange(&refresh_suppressed,0,0)) {
        InterlockedExchange(&dirty,1); InterlockedExchange(&requested,1);
        InterlockedExchange(&settle_ticks,0);
    }
}
static void load_hook(void *self,void *descriptor) {
    /* Keep a published snapshot through an in-career tournament hand-off.
     * A true save switch is still invalidated by the verified CareerContext
     * identity check before any card is published. */
    original_load(self,descriptor);
    if(!InterlockedCompareExchange(&refresh_suppressed,0,0)) {
        InterlockedExchange(&dirty,1); InterlockedExchange(&requested,1);
        InterlockedExchange(&settle_ticks,0);
    }
}
static void ready_hook(void *self,unsigned char ready) {
    if(!ready) invalidate();
    original_ready(self,ready); InterlockedExchange(&dirty,1);
    if(ready) {
        InterlockedExchange(&requested,1);
        InterlockedExchange(&settle_ticks,0);
    }
}
static int supported_file(HMODULE handle) {
    static const unsigned char expected[32]={
      0xf8,0xfe,0x0b,0x50,0xae,0xf0,0x28,0x08,0x52,0xd2,0xb9,0xe0,0xc2,0x16,0x81,0xe4,
      0x30,0x80,0x37,0x47,0x0e,0x48,0x7c,0x4e,0x1e,0xdd,0xc2,0xe0,0xda,0x00,0x70,0xed};
    wchar_t path[MAX_PATH]; FILE *f=NULL; unsigned char bytes[16384],digest[32];
    BCRYPT_ALG_HANDLE alg=NULL; BCRYPT_HASH_HANDLE hash=NULL;
    size_t n; int ok=0;
    if(!GetModuleFileNameW(handle,path,MAX_PATH)) return 0;
    f=_wfopen(path,L"rb"); if(!f) return 0;
    if(BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,NULL,0)<0 ||
       BCryptCreateHash(alg,&hash,NULL,0,NULL,0,0)<0) goto finish;
    while((n=fread(bytes,1,sizeof(bytes),f))>0)
        if(BCryptHashData(hash,bytes,(ULONG)n,0)<0) goto finish;
    if(ferror(f) || BCryptFinishHash(hash,digest,sizeof(digest),0)<0) goto finish;
    ok=memcmp(digest,expected,sizeof(digest))==0;
finish:
    if(hash) BCryptDestroyHash(hash);
    if(alg) BCryptCloseAlgorithmProvider(alg,0);
    fclose(f); return ok;
}
int fce_runtime_install(void) {
    HMODULE handle; void **v; DWORD protection,ignored; int result=0,installed_now=0; size_t i;
    static const unsigned rvas[14]={0x15160,0x8a5a0,0x13a00,0x16610,0x5ad20,0x4ea60,
      0x5ed50,0x46dc0,0x43430,0x4a040,0x4a820,0x5af50,0x44720,0x5cd90};
    handle=GetModuleHandleA("FootballCompEngzf.dll"); if(!handle) return 0;
    AcquireSRWLockExclusive(&install_lock);
    /* FootballCompEng is unloaded and loaded again while the first career is
     * generated.  Never keep a successful installation bound to the address
     * of the previous module instance. */
    if(installed==1 && module==(unsigned char *)handle) {
        /* Windows can unload/reload FootballCompEng at the same preferred
         * base while switching careers.  The address alone is therefore not
         * proof that our vtable hooks survived the transition. */
        v=(void **)(module+0x94360);
        if(v[4]==(void *)post_hook && v[5]==(void *)send_hook &&
           v[6]==(void *)update_hook && v[9]==(void *)load_hook &&
           v[11]==(void *)ready_hook) {
            result=1; goto done;
        }
        installed=0;
        original_post=NULL; original_send=NULL; original_update=NULL;
        original_load=NULL; original_ready=NULL;
        invalidate();
    }
    if(module!=(unsigned char *)handle) {
        installed=0;
        module=NULL;
        original_post=NULL; original_send=NULL; original_update=NULL;
        original_load=NULL; original_ready=NULL;
        invalidate();
    } else if(installed) { result=installed; goto done; }
    if(!supported_file(handle)) { result=-1; goto done; }
    module=(unsigned char *)handle; v=(void **)(module+0x94360);
    for(i=0;i<14;++i) if(v[i]!=module+rvas[i]) { result=-1; goto done; }
    original_post=(TwoFn)v[4]; original_send=(TwoFn)v[5]; original_update=(OneFn)v[6];
    original_load=(TwoFn)v[9]; original_ready=(ReadyFn)v[11];
    if(!VirtualProtect(v,14*sizeof(void *),PAGE_READWRITE,&protection)) { result=-1; goto done; }
    InterlockedExchangePointer((void *volatile *)(v+4),(void *)post_hook);
    InterlockedExchangePointer((void *volatile *)(v+5),(void *)send_hook);
    InterlockedExchangePointer((void *volatile *)(v+6),(void *)update_hook);
    InterlockedExchangePointer((void *volatile *)(v+9),(void *)load_hook);
    InterlockedExchangePointer((void *volatile *)(v+11),(void *)ready_hook);
    VirtualProtect(v,14*sizeof(void *),protection,&ignored);
    result=1; installed_now=1;
done:
    if(result) InterlockedExchange(&installed,result);
    if(result==1 && installed_now) {
        /* The first provider callback can arrive before the career service is
         * queryable.  Keep one capture queued so the owning Update thread
         * publishes the snapshot as soon as the new module settles. */
        InterlockedExchange(&requested,1);
        InterlockedExchange(&settle_ticks,0);
    }
    ReleaseSRWLockExclusive(&install_lock);
    if(installed_now || result<0) report("install",result,NULL,0);
    return result;
}
FceLiveSnapshot *fce_runtime_acquire(void) {
    FceLiveSnapshot *s; void *service=NULL,*iface=NULL,*registry;
    HMODULE pinned=NULL;
    if(fce_runtime_install()!=1) return NULL;
    /* Hold an OS loader reference across every access to module globals.  A
     * new-career transition may otherwise unload FootballCompEng between the
     * GetModuleHandle check and module+0xB13F0, producing the observed AV. */
    if(!GetModuleHandleExA(0,"FootballCompEngzf.dll",&pinned)) return NULL;
    if((unsigned char *)pinned!=module) {
        FreeLibrary(pinned);
        invalidate();
        return NULL;
    }
    /* Native registry contract: lookup holds a reference, QI returns the
     * same interface, and native callers release slot +8 exactly once. */
    __try {
        registry=*(void **)(module+0xb13f0);
        if(registry) service=((void *(*)(void *,unsigned))(*(void ***)registry)[8])(registry,0xa613b9a);
        if(service) iface=((void *(*)(void *,unsigned))(*(void ***)service)[3])(service,0xa613b9b);
        if(service) ((void (*)(void *))(*(void ***)service)[1])(service);
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        invalidate();
        InterlockedExchange(&requested,1);
        report("acquire_rejected",0,NULL,0);
    }
    FreeLibrary(pinned);
    if(!iface) {
        /* Loading a save legitimately exposes a short interval without the
         * registry service.  Do not repeatedly reset generation/settle state;
         * return an empty view and let update_hook satisfy the queued capture. */
        InterlockedExchange(&requested,1);
        return NULL;
    }
    AcquireSRWLockShared(&snapshot_lock);
    s=current; if(s) InterlockedIncrement(&s->refs);
    ReleaseSRWLockShared(&snapshot_lock);
    return s;
}
FceLiveSnapshot *fce_runtime_cached_acquire(void) {
    FceLiveSnapshot *s;
    AcquireSRWLockShared(&snapshot_lock);
    s=current; if(s) InterlockedIncrement(&s->refs);
    ReleaseSRWLockShared(&snapshot_lock);
    return s;
}
FceLiveSnapshot *fce_runtime_calendar_acquire(void) {
    FceLiveSnapshot *s;
    AcquireSRWLockShared(&snapshot_lock);
    s=calendar_current;if(s)InterlockedIncrement(&s->refs);
    ReleaseSRWLockShared(&snapshot_lock);
    return s;
}
int fce_runtime_is_stable(void) {
    return InterlockedCompareExchange(&settle_ticks,0,0)>=4 && pending_matches==0;
}
const FceModel *fce_runtime_model(const FceLiveSnapshot *s) { return s?&s->model:NULL; }
unsigned long fce_runtime_generation(const FceLiveSnapshot *s) { return s?s->generation:0; }
