#ifndef FIFA16_CAREER_JOBS_PROTOCOL_H
#define FIFA16_CAREER_JOBS_PROTOCOL_H
#include <stdint.h>
#define JOBS_MAGIC 0x164a4f42U
#define JOBS_VERSION 4U
#define JOBS_CAPACITY 16
typedef struct JobsShared {
    uint32_t magic,version,pid,ready,heartbeat;
    volatile int32_t sequence,completed,status;
    int32_t source_club,team,league,count;
    uint64_t registry,context;
    uint32_t error,load_epoch,request_epoch,reserved;
    int32_t clubs[JOBS_CAPACITY][2];
} JobsShared;
_Static_assert(sizeof(JobsShared)==208,"Career jobs IPC layout");
static int jobs_request_valid(const JobsShared *s,int club,uint64_t registry,uint64_t context)
{
    return s && s->source_club==club && club>0 && s->team>0 && s->team<2000000
        && s->team!=club && s->league>0 && s->league<2000000
        && s->registry==registry && s->context==context
        && s->request_epoch==s->load_epoch;
}
#endif
