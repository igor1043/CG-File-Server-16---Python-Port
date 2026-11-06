/* FIFA16 foreign leagues can retain the season definition without retaining
 * a scored fixture/standing row. ResponseStandingsList (FCE +0x6a810) then
 * calls +0x40ce0. Use that SAME calculation, on FCE's owner thread, once per
 * campaign revision. No screen object, UI input or career-file writes. */
typedef struct {
    void *vtable;
    unsigned char *begin,*end,*capacity;
    void *allocator;
    const char *label;
    int flags,padding;
} DerivedNativeVector;
_Static_assert(sizeof(DerivedNativeVector)==56,"FCE native standings vector ABI");
#ifndef DERIVED_ALLOCATOR
#define DERIVED_ALLOCATOR() ((void *(*)(void))(module+0x85030))()
#define DERIVED_GATHER(c,s,v) ((void (*)(void *,int,DerivedNativeVector *))(module+0x32290))(c,s,v)
#define DERIVED_CALCULATE(w,s,d,v) ((void (*)(void *,int,int,DerivedNativeVector *))(module+0x40ce0))(w,s,d,v)
#endif
#ifndef DERIVED_INTERFACE_READY
#define DERIVED_INTERFACE_READY(i) ((i) && *(void ***)(i)==(void **)(module+0x94360) && *((unsigned char *)(i)+0x30))
#endif
static SRWLOCK derived_lock=SRWLOCK_INIT;
static FceDerivedStanding *derived_rows;
static size_t derived_count,derived_capacity,derived_cursor,derived_jobs_count;
static int derived_jobs[6000],derived_date;
static LONG derived_epoch,derived_revision;
static unsigned long long derived_key;
static int derived_complete,derived_disabled;
static ULONGLONG derived_next;
#ifndef DERIVED_PHASE_IS_LEAGUE
static unsigned char derived_league_phases[65536];
static int derived_formats_loaded;
static int derived_phase_is_league(unsigned stage) {
    char path[MAX_PATH],line[512],key[128],mode[128],*slash;FILE *file;unsigned id;
    if(!derived_formats_loaded) {
        if(!GetModuleFileNameA((HMODULE)module,path,sizeof(path)))return 0;
        slash=strrchr(path,'\\');if(!slash)return 0;slash[1]=0;
        if(strlen(path)+strlen("data\\compdata\\settings.txt")>=sizeof(path))return 0;
        strcat(path,"data\\compdata\\settings.txt");file=fopen(path,"rb");if(!file)return 0;
        while(fgets(line,sizeof(line),file)) {
            if(sscanf(line,"%u,%127[^,],%127[^\r\n]",&id,key,mode)==3 && id<65536
                && !strcmp(key,"match_stagetype") && !strcmp(mode,"LEAGUE"))derived_league_phases[id]=1;
        }
        fclose(file);derived_formats_loaded=1;
    }
    return stage<65536 && derived_league_phases[stage];
}
#define DERIVED_PHASE_IS_LEAGUE(s) derived_phase_is_league(s)
#endif
static void derived_report(const char *event,int date,size_t jobs,size_t rows) {
    FILE *file=log_path[0]?fopen(log_path,"ab"):NULL;
    if(file){fprintf(file,"event=%s date=%d epoch=%ld phases=%llu rows=%llu\n",event,date,
        InterlockedCompareExchange(&generation,0,0),(unsigned long long)jobs,(unsigned long long)rows);fclose(file);}
}
static void derived_write(void) {
    char path[MAX_PATH],temporary[MAX_PATH],directory[MAX_PATH];FILE *file;
    FILETIME created,exited,kernel,user;ULARGE_INTEGER value;size_t i;int ok=1;
    if(!runtime_log_dir[0] || !GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user))return;
    value.LowPart=created.dwLowDateTime;value.HighPart=created.dwHighDateTime;
    snprintf(directory,sizeof(directory),"%s\\runtime",runtime_log_dir);CreateDirectoryA(directory,NULL);
    snprintf(path,sizeof(path),"%s\\career_derived_standings.json",directory);
    snprintf(temporary,sizeof(temporary),"%s\\career_derived_standings.%lu.tmp",directory,(unsigned long)GetCurrentProcessId());
    file=fopen(temporary,"wb");if(!file)return;
    AcquireSRWLockShared(&derived_lock);
    if(fprintf(file,"{\"schema\":1,\"pid\":%lu,\"created\":%llu,\"epoch\":%ld,\"date\":%d,\"revision\":%ld,\"rows\":[",
       (unsigned long)GetCurrentProcessId(),(unsigned long long)value.QuadPart,derived_epoch,derived_date,derived_revision)<0)ok=0;
    for(i=0;ok && i<derived_count;++i) {
        const FceDerivedStanding *d=derived_rows+i;const FceStanding *s=&d->standing;
        if(fprintf(file,"%s[%d,%d,%d,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u]",i?",":"",s->standing_id,s->competition_object,s->team,
            s->home_wins,s->home_draws,s->home_losses,s->away_wins,s->away_draws,s->away_losses,s->played,d->home_gf,d->home_ga,d->away_gf,d->away_ga)<0)ok=0;
    }
    ReleaseSRWLockShared(&derived_lock);
    if(fputs("]}",file)==EOF)ok=0;if(fclose(file)!=0)ok=0;
    if(ok)MoveFileExA(temporary,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);else DeleteFileA(temporary);
}
/* Stable content fingerprints: native table iteration order is not a result.
 * Per-root inputs include every node, standing and fixture in that campaign.
 * Date and career epoch are separate cache keys; never reuse another day/save. */
typedef struct {unsigned long long x,sum;size_t count;} DerivedFingerprint;
typedef struct {int slot,team;size_t index;} DerivedStandingIndex;
typedef struct {
    DerivedFingerprint *roots;
    unsigned char *played;
    DerivedStandingIndex *standing;
    size_t count;
} DerivedInputs;
typedef struct {
    int date;LONG epoch;unsigned long long key;
    FceDerivedStanding *rows;size_t count;int valid;
} DerivedPhaseCache;
static DerivedPhaseCache *derived_cache;
static LONG derived_cache_epoch;static int derived_cache_date;
static size_t derived_cache_rows;
static unsigned derived_reused,derived_calculated;
static ULONGLONG derived_native_ms;
static unsigned long long derived_hash(const void *raw,size_t bytes) {
    const unsigned char *p=raw;size_t i;unsigned long long h=1469598103934665603ULL;
    for(i=0;i<bytes;++i){h^=p[i];h*=1099511628211ULL;}return h;
}
static void derived_fingerprint(DerivedFingerprint *f,const void *row,size_t size,unsigned tag) {
    unsigned long long h=derived_hash(row,size)^((unsigned long long)tag*0x9e3779b97f4a7c15ULL);
    h^=h>>30;h*=0xbf58476d1ce4e5b9ULL;h^=h>>27;h*=0x94d049bb133111ebULL;h^=h>>31;
    f->x^=h;f->sum+=h;++f->count;
}
static unsigned long long derived_fingerprint_key(const DerivedFingerprint *f) {
    return f->x^(f->sum*0x9e3779b97f4a7c15ULL)^((unsigned long long)f->count*0xbf58476d1ce4e5b9ULL);
}
static unsigned long long derived_signature(const FceModel *m) {
    DerivedFingerprint f={0};size_t i;
    for(i=0;i<m->node_count;++i)derived_fingerprint(&f,m->nodes+i,sizeof(*m->nodes),1);
    for(i=0;i<m->standing_count;++i)derived_fingerprint(&f,m->standings+i,sizeof(*m->standings),2);
    for(i=0;i<m->fixture_count;++i)derived_fingerprint(&f,m->fixtures+i,sizeof(*m->fixtures),3);
    return derived_fingerprint_key(&f);
}
static int derived_standing_order(const void *a,const void *b) {
    const DerivedStandingIndex *x=a,*y=b;
    if(x->slot!=y->slot)return (x->slot>y->slot)-(x->slot<y->slot);
    if(x->team!=y->team)return (x->team>y->team)-(x->team<y->team);
    return (x->index>y->index)-(x->index<y->index);
}
static void derived_inputs_free(DerivedInputs *in) {
    free(in->roots);free(in->played);free(in->standing);memset(in,0,sizeof(*in));
}
static int derived_inputs_build(const FceModel *m,DerivedInputs *in) {
    size_t i;
    in->roots=calloc(65536,sizeof(*in->roots));in->played=calloc(65536,1);
    in->standing=calloc(m->standing_count?m->standing_count:1,sizeof(*in->standing));
    if(!in->roots||!in->played||!in->standing){derived_inputs_free(in);return 0;}
    for(i=0;i<m->node_count;++i) {
        int root=fce_model_ancestor(m,m->nodes[i].id,3);
        if(root>=0&&root<65536)derived_fingerprint(in->roots+root,m->nodes+i,sizeof(*m->nodes),1);
    }
    for(i=0;i<m->standing_count;++i) {
        const FceStanding *s=m->standings+i;int root=fce_model_ancestor(m,s->competition_object,3);
        int stage=fce_model_ancestor(m,s->competition_object,4);
        if(root>=0&&root<65536)derived_fingerprint(in->roots+root,s,sizeof(*s),2);
        if(stage>=0&&stage<65536&&s->played)in->played[stage]=1;
        in->standing[i]=(DerivedStandingIndex){s->standing_id,s->team,i};
    }
    for(i=0;i<m->fixture_count;++i) {
        int root=fce_model_ancestor(m,m->fixtures[i].competition_object,3);
        if(root>=0&&root<65536)derived_fingerprint(in->roots+root,m->fixtures+i,sizeof(*m->fixtures),3);
    }
    in->count=m->standing_count;qsort(in->standing,in->count,sizeof(*in->standing),derived_standing_order);return 1;
}
static const FceStanding *derived_find(const FceModel *m,const DerivedInputs *in,int slot,int team) {
    size_t lo=0,hi=in->count;
    while(lo<hi){size_t mid=lo+(hi-lo)/2;const DerivedStandingIndex *r=in->standing+mid;
        if(r->slot<slot||(r->slot==slot&&r->team<team))lo=mid+1;else hi=mid;}
    if(lo<in->count&&in->standing[lo].slot==slot&&in->standing[lo].team==team)return m->standings+in->standing[lo].index;
    return NULL;
}
static int derived_append(const FceDerivedStanding *rows,size_t count) {
    int ok=1;AcquireSRWLockExclusive(&derived_lock);
    if(count>65536-derived_count)ok=0;
    if(ok && derived_count+count>derived_capacity) {
        size_t capacity=derived_count+count;FceDerivedStanding *p=realloc(derived_rows,capacity*sizeof(*p));
        if(p){derived_rows=p;derived_capacity=capacity;}else ok=0;
    }
    if(ok&&count){memcpy(derived_rows+derived_count,rows,count*sizeof(*rows));derived_count+=count;}
    ReleaseSRWLockExclusive(&derived_lock);return ok;
}
unsigned long fce_runtime_derived_revision(void) {
    return (unsigned long)InterlockedCompareExchange(&derived_revision,0,0);
}
size_t fce_runtime_derived_copy(FceDerivedStanding *out,size_t capacity,int date) {
    size_t n=0;
    AcquireSRWLockShared(&derived_lock);
    if(derived_complete && !derived_disabled && derived_date==date &&
       derived_epoch==InterlockedCompareExchange(&generation,0,0)) {
        n=derived_count;
        if(out) {if(capacity<n)n=capacity;memcpy(out,derived_rows,n*sizeof(*out));}
    }
    ReleaseSRWLockShared(&derived_lock);return n;
}
static int derived_i32(const unsigned char *p,size_t offset) {
    int v;memcpy(&v,p+offset,sizeof(v));return v;
}
static void derived_free_vector(DerivedNativeVector *v) {
    if(v->begin && v->allocator) {
        void **methods=*(void ***)v->allocator;
        ((void (*)(void *,void *,size_t))methods[3])(v->allocator,v->begin,0);
    }
    memset(v,0,sizeof(*v));
}
static void derived_step(void *iface,unsigned long long *batch_key,int *key_ready,DerivedInputs *inputs) {
    FceLiveSnapshot *snapshot;const FceModel *m;
    unsigned char *hub,*connector,*manager,*list,**first,**last;
    void *clock=NULL;void *wrapper[3];FceRawTable competitions={0};
    unsigned long long key,phase_key=0;size_t i,j,n,first_row=0;int stage,root,failed=0;
    DerivedPhaseCache *cached=NULL;ULONGLONG native_started;
    LONG epoch=InterlockedCompareExchange(&generation,0,0);
    DerivedNativeVector vector={0};ULONGLONG started=GetTickCount64();
    snapshot=fce_runtime_calendar_acquire();
    if(!snapshot && fce_runtime_is_stable())snapshot=fce_runtime_cached_acquire();
    if(!snapshot)return;m=&snapshot->model;
    if(date_callback && date_callback()!=m->date){fce_runtime_release(snapshot);return;}
    /* Immutable owner-thread snapshot: hash once for this complete batch. */
    if(!*key_ready){*batch_key=derived_signature(m);*key_ready=1;}
    key=*batch_key;
    if(derived_epoch==epoch && derived_date==m->date && derived_key==key &&
       (derived_complete||derived_disabled)){fce_runtime_release(snapshot);return;}
    if(!inputs->roots && !derived_inputs_build(m,inputs)){fce_runtime_release(snapshot);return;}
    __try {
        if(!DERIVED_INTERFACE_READY(iface))__leave;
        hub=*(unsigned char **)((unsigned char *)iface+0x18);
        connector=*(unsigned char **)(hub+0x28);manager=*(unsigned char **)(connector+0x18);
        list=*(unsigned char **)(hub+0x20);first=*(unsigned char ***)(list+8);last=*(unsigned char ***)(list+0x10);
        if(last<first || last-first>16) __leave;
        for(;first<last;++first)if(*first && *(int *)(*first+0x20)==5){clock=*first;break;}
        if(!clock || !fce_date_valid(m->date))__leave;
        if(derived_epoch!=epoch || derived_date!=m->date || derived_key!=key) {
            if(!copy_table(manager,0x48,&competitions))__leave;
            AcquireSRWLockExclusive(&derived_lock);
            derived_epoch=epoch;derived_date=m->date;derived_key=key;
            derived_count=derived_cursor=derived_jobs_count=0;derived_complete=derived_disabled=0;
            InterlockedIncrement(&derived_revision);
            for(i=0;i<competitions.count && derived_jobs_count<6000;++i) {
                const unsigned char *p=competitions.bytes+i*competitions.stride;
                unsigned id=(unsigned)p[0x10]+256*(unsigned)p[0x11];
                if(competitions.stride<0x16 || p[0xa]!=1 || p[0x12]!=4 || !DERIVED_PHASE_IS_LEAGUE(id))continue;
                derived_jobs[derived_jobs_count++]=(int)id;
            }
            ReleaseSRWLockExclusive(&derived_lock);
            free((void *)competitions.bytes);competitions.bytes=NULL;
            derived_report("derived_standings_started",m->date,derived_jobs_count,0);
            if(!derived_cache)derived_cache=calloc(65536,sizeof(*derived_cache));
            if(derived_cache&&(derived_cache_epoch!=epoch||derived_cache_date!=m->date)) {
                for(i=0;i<65536;++i){free(derived_cache[i].rows);memset(derived_cache+i,0,sizeof(*derived_cache));}
                derived_cache_rows=0;derived_cache_epoch=epoch;derived_cache_date=m->date;
            }
        }
        if(derived_cursor>=derived_jobs_count) {
            AcquireSRWLockExclusive(&derived_lock);derived_complete=1;ReleaseSRWLockExclusive(&derived_lock);
            InterlockedIncrement(&derived_revision);derived_write();fce_runtime_request_refresh();
            derived_report("derived_standings_complete",m->date,derived_jobs_count,derived_count);__leave;
        }
        stage=derived_jobs[derived_cursor++];
        /* Exactly as ResponseStandingsList: an actual score in this phase
         * takes precedence. Never run the fallback over a played campaign. */
        if(stage<0||stage>=65536 || inputs->played[stage])__leave;
        root=fce_model_ancestor(m,stage,3);
        if(derived_cache && root>=0&&root<65536) {
            phase_key=derived_fingerprint_key(inputs->roots+root);cached=derived_cache+stage;
            if(cached->valid&&cached->date==m->date&&cached->epoch==epoch&&cached->key==phase_key) {
                if(!derived_append(cached->rows,cached->count))failed=1;else ++derived_reused;
                __leave;
            }
        }
        first_row=derived_count;
        vector.vtable=module+0x907e8;
        vector.allocator=DERIVED_ALLOCATOR();
        vector.label="Server16 career standings";
        native_started=GetTickCount64();
        DERIVED_GATHER(connector,stage,&vector);
        derived_native_ms+=GetTickCount64()-native_started;
        if(!vector.begin || vector.end<vector.begin || (size_t)(vector.end-vector.begin)%0x9c)__leave;
        n=(size_t)(vector.end-vector.begin)/0x9c;
        if(n<2 || n>256)__leave;
        for(i=0;i<n;++i)if(derived_i32(vector.begin+i*0x9c,4)<=0)__leave;
        wrapper[0]=connector;wrapper[1]=clock;wrapper[2]=hub;
        native_started=GetTickCount64();
        DERIVED_CALCULATE(wrapper,stage,m->date,&vector);
        derived_native_ms+=GetTickCount64()-native_started;++derived_calculated;
        for(i=0;i<n;++i) {
            const unsigned char *p=vector.begin+i*0x9c;
            int slot=derived_i32(p,0),team=derived_i32(p,4);FceDerivedStanding row;const FceStanding *standing;
            unsigned values[10];static const size_t offsets[]={0x74,0x78,0x7c,0x88,0x8c,0x90,0x80,0x84,0x94,0x98};
            for(j=0;j<10;++j){int v=derived_i32(p,offsets[j]);if(v<0||v>1000){failed=1;break;}values[j]=(unsigned)v;}
            if(failed)break;
            standing=derived_find(m,inputs,slot,team);
            if(!standing){failed=1;break;}
            memset(&row,0,sizeof(row));row.standing=*standing;
            row.standing.home_wins=values[0];row.standing.home_draws=values[1];row.standing.home_losses=values[2];
            row.standing.away_wins=values[3];row.standing.away_draws=values[4];row.standing.away_losses=values[5];
            row.standing.played=values[0]+values[1]+values[2]+values[3]+values[4]+values[5];
            row.home_gf=values[6];row.home_ga=values[7];row.away_gf=values[8];row.away_ga=values[9];
            if(!row.standing.played)continue;
            if(!derived_append(&row,1)){failed=1;break;}
        }
        if(!failed&&cached) {
            size_t count=derived_count-first_row;
            /* Optional cache is bounded by the same 65,536 rows as publication.
             * Allocation failure keeps correct uncached behaviour. */
            if(count<=65536-(derived_cache_rows-cached->count)) {
                FceDerivedStanding *copy=count?malloc(count*sizeof(*copy)):NULL;
                if(!count||copy) {
                    if(count)memcpy(copy,derived_rows+first_row,count*sizeof(*copy));
                    derived_cache_rows=derived_cache_rows-cached->count+count;
                    free(cached->rows);*cached=(DerivedPhaseCache){m->date,epoch,phase_key,copy,count,1};
                }
            }
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {failed=1;}
    __try {derived_free_vector(&vector);} __except(EXCEPTION_EXECUTE_HANDLER) {failed=1;}
    if(competitions.bytes)free((void *)competitions.bytes);
    if(failed) {
        AcquireSRWLockExclusive(&derived_lock);derived_disabled=1;derived_count=0;ReleaseSRWLockExclusive(&derived_lock);
        report("derived_standings_rejected",0,m,GetTickCount64()-started);
    }
    /* Allocation, calculation and release stay on the verified FCE owner. */
    fce_runtime_release(snapshot);
}

/* Finish the bounded phase set before returning to the calendar owner.
 * Splitting 145 phases into eight-phase frames starved fast daily advances:
 * the following day invalidated the unfinished previous day's campaign.
 * Native calculation/allocation/release remain on the verified owner thread.
 * No mutable pointers or partial results are published to worker threads. */
static void derived_tick(void *iface) {
    ULONGLONG tick=GetTickCount64();unsigned count;int key_ready=0;
    unsigned long long key=0;DerivedInputs inputs={0};
    int observed=date_callback?date_callback():derived_date;
    if(tick<derived_next && observed==derived_date)return;
    derived_reused=derived_calculated=0;derived_native_ms=0;
    for(count=0;count<=6000;++count) {
        size_t previous=derived_cursor;LONG revision=derived_revision;
        derived_step(iface,&key,&key_ready,&inputs);
        if(derived_complete || derived_disabled || (previous==derived_cursor && revision==derived_revision))break;
    }
    derived_inputs_free(&inputs);
    if(count && log_path[0]) {
        FILE *file=fopen(log_path,"ab");
        if(file){fprintf(file,"event=derived_standings_batch date=%d phases=%llu complete=%d elapsed_ms=%llu calculated=%u reused=%u native_ms=%llu\n",derived_date,(unsigned long long)derived_cursor,derived_complete,(unsigned long long)(GetTickCount64()-tick),derived_calculated,derived_reused,(unsigned long long)derived_native_ms);fclose(file);}
    }
    derived_next=GetTickCount64()+16;
}
