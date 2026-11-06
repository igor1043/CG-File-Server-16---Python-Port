#ifndef FIFA16_CARD_REFRESH_SCHEDULE_H
#define FIFA16_CARD_REFRESH_SCHEDULE_H
#include <stdint.h>
#include <string.h>

/* Data revisions and native view entries are independent. A new view must
 * receive the same payload again, even if no career data changed. Retries are
 * consumed before re-entry and never rearmed by an automatic publication. */
typedef struct CardRefreshSchedule {
    unsigned long applied_generation;
    unsigned long requested_generation;
    unsigned long view_revision;
    uint64_t entered_at;
    uint64_t next_data_attempt;
    unsigned settle_attempts;
    unsigned data_attempts;
    int data_pending;
} CardRefreshSchedule;

static void card_refresh_enter(CardRefreshSchedule *s, uint64_t now)
{
    unsigned long revision = s->view_revision + 1;
    memset(s, 0, sizeof(*s));
    s->view_revision = revision ? revision : 1;
    s->entered_at = now;
}

static void card_refresh_applied(CardRefreshSchedule *s, unsigned long generation)
{
    if (!generation) return;
    s->applied_generation = generation;
    if (generation >= s->requested_generation) s->data_pending = 0;
}

static void card_refresh_request(CardRefreshSchedule *s,
    unsigned long generation, uint64_t now)
{
    if (!generation || generation <= s->applied_generation ||
        generation <= s->requested_generation) return;
    s->requested_generation = generation;
    s->data_attempts = 0;
    s->data_pending = 1;
    s->next_data_attempt = now;
}

/* Return a reason bitmask: 1 = view settling, 2 = new data. No timer/worker
 * touches FIFA objects; the caller drains this on the native owner thread. */
static unsigned card_refresh_take_due(CardRefreshSchedule *s, uint64_t now)
{
    static const unsigned delays[] = {80, 250, 650};
    unsigned reason = 0;
    if (!s->view_revision) return 0;
    if (s->settle_attempts < 3 &&
        now >= s->entered_at + delays[s->settle_attempts]) {
        ++s->settle_attempts;
        /* Do not burst three rebuilds after a paused/minimized game. */
        while (s->settle_attempts < 3 &&
            now >= s->entered_at + delays[s->settle_attempts])
            ++s->settle_attempts;
        reason |= 1;
    }
    if (s->data_pending && s->data_attempts < 3 &&
        now >= s->next_data_attempt) {
        ++s->data_attempts;
        s->next_data_attempt = now + 250;
        reason |= 2;
    }
    return reason;
}
#endif
