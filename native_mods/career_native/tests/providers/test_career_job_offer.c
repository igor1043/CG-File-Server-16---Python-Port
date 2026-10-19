#include <assert.h>
#include <stdio.h>
#include "../../src/host/career_job_offer.h"
int main(void)
{
    int offer[11]={383,7,0,0,0,0,20260409,38000,1043,CAREER_JOB_OFFER_MARKER,-1};
    assert(career_job_offer_pending(offer,1043));
    assert(!career_job_offer_pending(offer,383));
    assert(!career_job_offer_pending(offer,598));
    offer[10]=1; assert(!career_job_offer_pending(offer,1043)); offer[10]=-1;
    offer[9]=38000; assert(!career_job_offer_pending(offer,1043));
    offer[9]=CAREER_JOB_OFFER_MARKER;
    career_job_offer_consume(offer);
    assert(!career_job_offer_pending(offer,1043));
    assert(offer[0]==383 && offer[1]==7 && offer[8]==-1 && offer[9]==-1 && offer[10]==-1);
    puts("PASS: only marked offers for the loaded career dispatch; consume prevents duplicate delivery");
    return 0;
}
