#include "../../src/host/card_refresh_schedule.h"
#include <stdio.h>

#define CHECK(test) do { if (!(test)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #test); return 1; \
} } while (0)

int main(void)
{
    CardRefreshSchedule s = {0};
    CHECK(card_refresh_take_due(&s, 100000) == 0);

    card_refresh_enter(&s, 1000);
    card_refresh_applied(&s, 7);
    CHECK(card_refresh_take_due(&s, 1079) == 0);
    CHECK(card_refresh_take_due(&s, 1080) == 1);
    card_refresh_applied(&s, 7);
    CHECK(card_refresh_take_due(&s, 1081) == 0);
    CHECK(card_refresh_take_due(&s, 1250) == 1);
    CHECK(card_refresh_take_due(&s, 1650) == 1);
    CHECK(card_refresh_take_due(&s, 100000) == 0);

    /* Re-entering with unchanged data still rebuilds the new native view. */
    card_refresh_enter(&s, 2000);
    CHECK(s.view_revision == 2 && s.applied_generation == 0);
    card_refresh_applied(&s, 7);
    card_refresh_request(&s, 7, 2000);
    CHECK(card_refresh_take_due(&s, 2080) == 1);

    /* A failed/null payload never acknowledges a new generation. */
    card_refresh_request(&s, 8, 2100);
    CHECK(card_refresh_take_due(&s, 2100) == 2);
    card_refresh_applied(&s, 0);
    CHECK(s.applied_generation == 7 && s.data_pending);
    CHECK(card_refresh_take_due(&s, 2250) == 1);
    CHECK(card_refresh_take_due(&s, 2350) == 2);
    card_refresh_applied(&s, 8);
    CHECK(!s.data_pending);
    card_refresh_request(&s, 7, 2500);
    CHECK(!s.data_pending && s.applied_generation == 8);
    CHECK(card_refresh_take_due(&s, 2600) == 0);
    CHECK(card_refresh_take_due(&s, 2650) == 1);

    /* Exhausted data retries cannot be rearmed by the same callback. */
    card_refresh_request(&s, 9, 3000);
    CHECK(card_refresh_take_due(&s, 3000) == 2);
    CHECK(card_refresh_take_due(&s, 3250) == 2);
    CHECK(card_refresh_take_due(&s, 3500) == 2);
    card_refresh_request(&s, 9, 4000);
    CHECK(card_refresh_take_due(&s, 4000) == 0);
    card_refresh_request(&s, 10, 4100);
    CHECK(card_refresh_take_due(&s, 4100) == 2);

    /* Navigation supersedes old pending work, including an absent payload. */
    card_refresh_enter(&s, 5000);
    CHECK(!s.data_pending && !s.applied_generation);
    CHECK(card_refresh_take_due(&s, 5079) == 0);
    CHECK(card_refresh_take_due(&s, 5080) == 1);
    CHECK(card_refresh_take_due(&s, 5250) == 1);
    CHECK(card_refresh_take_due(&s, 5650) == 1);
    CHECK(card_refresh_take_due(&s, 100000) == 0);

    /* A paused game coalesces overdue attempts into one rebuild. */
    card_refresh_enter(&s, 6000);
    CHECK(card_refresh_take_due(&s, 100000) == 1);
    CHECK(card_refresh_take_due(&s, 100000) == 0);
    memset(&s, 0, sizeof(s));
    CHECK(card_refresh_take_due(&s, 100000) == 0);
    puts("PASS: unchanged views, pending publication, bounded retries, navigation and pause.");
    return 0;
}
