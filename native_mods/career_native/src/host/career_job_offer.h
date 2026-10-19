#ifndef FIFA16_CAREER_JOB_OFFER_H
#define FIFA16_CAREER_JOB_OFFER_H
/* Last three jo002 integers are the native pending application. A negative
 * salary and inactive countdown distinguish an offline, confirmed mod request
 * from every ordinary FIFA application. Never touch ordinary offers. */
#define CAREER_JOB_OFFER_MARKER (-16416)
static int career_job_offer_pending(const int *offer, int current_club)
{
    return offer && current_club > 0 && offer[0] > 0
        && offer[0] != current_club && offer[1] > 0
        && offer[6] >= 20000101 && offer[6] <= 20991231
        && offer[7] > 0 && offer[8] == current_club
        && offer[9] == CAREER_JOB_OFFER_MARKER && offer[10] == -1;
}
static void career_job_offer_consume(int *offer)
{
    offer[8] = offer[9] = offer[10] = -1;
}
#endif
