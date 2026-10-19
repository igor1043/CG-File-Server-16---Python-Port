#include "career_job_offer.h"
typedef void (*CareerJobGatherFn)(void *, int, int, int *);
typedef void (*CareerJobAddFn)(void *, const int *, int);
typedef void (*CareerJobInformFn)(void *, int *, unsigned char);
static LONG g_career_job_dispatch_busy;

/* Called after StatisticsData returns, on FIFA's provider owner thread.
 * Offline publication only stages jo002. Native FIFA creates the real club
 * details, salary, email and JobOffer event here after the career is loaded. */
static void career_job_offer_deliver(void *owner)
{
    static const unsigned char gather_head[] = {0x48,0x89,0x5c,0x24,0x18};
    static const unsigned char offer_head[] = {0x48,0x89,0x5c,0x24,0x08};
    unsigned char *manager;
    void *standings;
    int *offer;
    int club, team_record[10], league, target, i;
    uintptr_t begin, end, cursor;
    if (!g_module_base || g_module_size <= 0x05bd0030 || !owner
        || !fce_runtime_is_stable()
        || InterlockedCompareExchange(&g_career_job_dispatch_busy,1,0)) return;
    __try {
        manager = (unsigned char *)owner_service(owner,
            (GetServiceDescriptorFn)(g_module_base+0x04456a60),NULL);
        if (!is_readable_range(manager,0x188)
            || *(uintptr_t *)manager != (uintptr_t)(g_module_base+0x03071270)
            || *(uintptr_t *)(manager+0x150) != (uintptr_t)(g_module_base+0x03071250)) __leave;
        offer = (int *)(manager+0x158);
        club = resolve_user_club_id(owner,NULL);
        if (!career_job_offer_pending(offer,club)) __leave;
        if (memcmp(g_module_base+0x05aa4120,gather_head,sizeof(gather_head))
            || memcmp(g_module_base+0x05b57860,offer_head,sizeof(offer_head))
            || memcmp(g_module_base+0x05bcfaa0,offer_head,sizeof(offer_head))) __leave;
        standings = owner_service(owner,
            (GetServiceDescriptorFn)(g_module_base+0x044570e0),NULL);
        if (!standings) __leave;
        target=offer[0]; league=offer[1];
        for(i=0;i<10;++i) team_record[i]=-1;
        ((CareerJobGatherFn)(g_module_base+0x05aa4120))(standings,target,
            *(int *)(manager+0x144),team_record);
        if (team_record[4]!=target) __leave;
        /* AddOffer uses native standings and the native league wage rule. */
        ((CareerJobAddFn)(g_module_base+0x05b57860))(manager,team_record,league);
        begin=*(uintptr_t *)(manager+0xd8);end=*(uintptr_t *)(manager+0xe0);
        if (end<begin || end-begin>4096U*32U || (end-begin)%32U
            || !is_readable_range((const void *)begin,end-begin)) __leave;
        for(cursor=begin;cursor<end;cursor+=32U) {
            const int *row=(const int *)cursor;
            if(row[0]!=target || row[1]!=league || row[7]<=0) continue;
            memcpy(offer,row,32U);
            /* Consume before native event delivery to prevent reentrant mail. */
            career_job_offer_consume(offer);
            ((CareerJobInformFn)(g_module_base+0x05bcfaa0))(manager,offer,1);
            append_loader_log("career_job_offer_native_email_dispatched");
            /* Loading a legacy marker must not replay a generic toast.
             * Current requests are acknowledged once by Server16 after the
             * native contract queue confirms that specific request. */
            break;
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        append_loader_log("career_job_offer_delivery_guarded");
    }
    InterlockedExchange(&g_career_job_dispatch_busy,0);
}
