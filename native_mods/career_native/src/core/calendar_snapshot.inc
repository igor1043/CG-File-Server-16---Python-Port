/* Read-only calendar evidence. No provider calls, native allocation, ready
 * callback, save writes, or relaxation of the existing visual settle gate. */
static ULONGLONG calendar_next;
static LONG calendar_epoch;
static int calendar_day;
static unsigned long long calendar_key;
static unsigned long long calendar_signature(const FceRawTable *tables,int date) {
    unsigned long long hash=1469598103934665603ULL;size_t i,j;
    hash^=(unsigned)date;hash*=1099511628211ULL;
    for(i=0;i<4;++i) {
        hash^=tables[i].stride;hash*=1099511628211ULL;
        hash^=tables[i].count;hash*=1099511628211ULL;
        for(j=0;j<tables[i].count*tables[i].stride;++j){hash^=tables[i].bytes[j];hash*=1099511628211ULL;}
    }
    return hash;
}
static void calendar_capture(void *iface) {
    FceRawTable tables[4]={{0}};FceLiveSnapshot *next=NULL,*old;
    unsigned char *hub,*connector,*manager;int date=-1,ok=0;size_t i;
    unsigned long long key=0;LONG epoch=InterlockedCompareExchange(&generation,0,0);
    ULONGLONG now=GetTickCount64();
    if(GetCurrentThreadId()!=engine_thread || !date_callback)return;
    __try {
        date=date_callback();
        if(!fce_date_valid(date))__leave;
        if(epoch==calendar_epoch && date==calendar_day && now<calendar_next)__leave;
        calendar_next=now+250;calendar_day=date;calendar_epoch=epoch;
        if(!iface || *(void ***)iface!=(void **)(module+0x94360) || !*((unsigned char *)iface+0x30))__leave;
        hub=*(unsigned char **)((unsigned char *)iface+0x18);if(!hub)__leave;
        connector=*(unsigned char **)(hub+0x28);if(!connector)__leave;
        manager=*(unsigned char **)(connector+0x18);if(!manager)__leave;
        if(!copy_table(manager,0x48,tables) || !copy_table(manager,0x80,tables+1)
            || !copy_table(manager,0x58,tables+3))__leave;
        tables[2].stride=0x25; /* Player statistics are deliberately omitted. */
        if(date_callback()!=date || epoch!=InterlockedCompareExchange(&generation,0,0))__leave;
        key=calendar_signature(tables,date);
        if(calendar_current && calendar_key==key)__leave;
        ok=1;
    } __except(EXCEPTION_EXECUTE_HANDLER) {ok=0;}
    if(ok) {
        next=calloc(1,sizeof(*next));
        if(next){next->refs=1;ok=fce_model_build(tables,date,&next->model)==FCE_OK;}else ok=0;
    }
    for(i=0;i<4;++i)free((void *)tables[i].bytes);
    if(ok && epoch==InterlockedCompareExchange(&generation,0,0)) {
        next->generation=(unsigned long)InterlockedIncrement(&publication_revision);
        AcquireSRWLockExclusive(&snapshot_lock);
        old=calendar_current;calendar_current=next;calendar_key=key;
        ReleaseSRWLockExclusive(&snapshot_lock);
        fce_runtime_release(old);
    } else fce_runtime_release(next);
}
