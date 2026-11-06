/* Read-only service identity for external readers. Unlike a deferred card
 * owner this remains available on financial/mail screens. Readers verify the
 * sequence, registry entry, service vtable and current selected context. */
typedef struct CareerContextRead {
    DWORD schema, size;
    volatile LONG sequence;
    DWORD pid;
    uintptr_t service, vtable, registry;
    DWORD epoch, owner_thread;
} CareerContextRead;
__declspec(dllexport) CareerContextRead Fifa16CareerContextRead = {
    1, sizeof(CareerContextRead), 0, 0, 0, 0, 0, 0, 0
};
static SRWLOCK g_context_read_lock=SRWLOCK_INIT;
static int career_context_calendar_date(void)
{
    CareerContextRead captured;uintptr_t wrapper=0,calendar=0;unsigned index;int parts[3],date=-1;
    AcquireSRWLockShared(&g_context_read_lock);
    memcpy(&captured,&Fifa16CareerContextRead,sizeof(captured));
    ReleaseSRWLockShared(&g_context_read_lock);
    if(captured.sequence&1 || captured.pid!=GetCurrentProcessId()
        || captured.epoch!=fce_runtime_context_epoch() || !captured.registry)return -1;
    __try {
        if(!is_readable_range((void *)captured.service,32) || *(uintptr_t *)captured.service!=captured.vtable
            || memcmp(g_module_base+0x44563f0+7,"\xc7\x01",2))return -1;
        memcpy(&index,g_module_base+0x44563f0+9,sizeof(index));
        if(index>255 || !is_readable_range((void *)(captured.registry+(uintptr_t)index*32+24),8))return -1;
        wrapper=*(uintptr_t *)(captured.registry+(uintptr_t)index*32+24);
        if(!is_readable_range((void *)wrapper,8))return -1;
        calendar=*(uintptr_t *)wrapper;
        if(!is_readable_range((void *)calendar,0x40))return -1;
        memcpy(parts,(void *)(calendar+0x34),sizeof(parts));date=fce_date_pack(parts[0],parts[1],parts[2]);
        if(!fce_date_valid(date) || Fifa16CareerContextRead.sequence!=captured.sequence)return -1;
    } __except(EXCEPTION_EXECUTE_HANDLER) {return -1;}
    return date;
}
static void publish_career_context_read(void *service, void *owner)
{
    uintptr_t vtable = 0, registry = 0;
    if (!is_readable_range(service, 32) || !is_readable_range(owner, 16)) return;
    memcpy(&vtable, service, sizeof(vtable));
    memcpy(&registry, (unsigned char *)owner + 8, sizeof(registry));
    if (!vtable || !registry) return;
    AcquireSRWLockExclusive(&g_context_read_lock);
    if (Fifa16CareerContextRead.service==(uintptr_t)service
        && Fifa16CareerContextRead.vtable==vtable && Fifa16CareerContextRead.registry==registry
        && Fifa16CareerContextRead.epoch==fce_runtime_context_epoch()
        && Fifa16CareerContextRead.owner_thread==GetCurrentThreadId()) {
        ReleaseSRWLockExclusive(&g_context_read_lock);return;
    }
    InterlockedIncrement(&Fifa16CareerContextRead.sequence);
    Fifa16CareerContextRead.pid = GetCurrentProcessId();
    Fifa16CareerContextRead.service = (uintptr_t)service;
    Fifa16CareerContextRead.vtable = vtable;
    Fifa16CareerContextRead.registry = registry;
    Fifa16CareerContextRead.epoch = fce_runtime_context_epoch();
    Fifa16CareerContextRead.owner_thread = GetCurrentThreadId();
    InterlockedIncrement(&Fifa16CareerContextRead.sequence);
    ReleaseSRWLockExclusive(&g_context_read_lock);
}
