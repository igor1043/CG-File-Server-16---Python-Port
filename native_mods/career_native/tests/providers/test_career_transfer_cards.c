#include <assert.h>
#include <stdio.h>
#include "../../src/host/career_transfer_cards.h"
static int observed_first,observed_end,observed_latest,calls;
static void *observed_owner,*observed_provider,*observed_deals;
static void original(void *owner,void *provider,int first,int end,void *deals,int latest)
{
    observed_owner=owner;observed_provider=provider;observed_deals=deals;
    observed_first=first;observed_end=end;observed_latest=latest;++calls;
}
int main(void)
{
    int owner=1,provider=2,deals=3;
    career_transfer_cards_publish(&owner,&provider,0,3,&deals,0);
    assert(!calls);
    g_transfer_cards_publish=original;
    career_transfer_cards_publish(&owner,&provider,0,3,&deals,0);
    assert(calls==1 && observed_first==0 && observed_end==10 && observed_latest==0);
    assert(observed_owner==&owner && observed_provider==&provider && observed_deals==&deals);
    career_transfer_cards_publish(&owner,&provider,3,6,&deals,1);
    assert(calls==2 && observed_first==3 && observed_end==13 && observed_latest==1);
    career_transfer_cards_publish(&owner,&provider,4,7,&deals,1);
    assert(observed_first==4 && observed_end==7);
    career_transfer_cards_publish(&owner,&provider,0,3,&deals,2);
    assert(observed_first==0 && observed_end==3 && observed_latest==2);
    career_transfer_cards_publish(&owner,&provider,0,10,&deals,0);
    assert(observed_first==0 && observed_end==10);
    puts("PASS: ten top/latest transfers; native ID ranges, arguments and unknown calls preserved");
    return 0;
}
