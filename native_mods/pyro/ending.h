#pragma once
#include <stdint.h>
#include "launch_sites.h"
// Stop matched pairs over five seconds, then allow the 6.5s particles to drain.
// The tail is INCLUDED in the original 60s/25s show, not added to gameplay.
static bool pyro_drain_due(uint64_t now,uint64_t start,bool goal,int index,uint64_t duration=0) {
    const int count=goal?pyroGoalCount:pyroIntroCount;
    if(now<start || index<0 || index>=count)return false;
    const uint64_t length=duration?duration:(goal?25000ULL:60000ULL);
    if(length<12000ULL)return now-start>=length;
    const uint64_t due=length-12000ULL+(uint64_t)(index/2)*5000ULL/(uint64_t)(count/2-1);
    return now-start>=due;
}
