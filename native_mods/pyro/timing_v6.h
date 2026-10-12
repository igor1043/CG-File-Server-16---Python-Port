#pragma once
#include <stdint.h>
static bool pyro_expired(uint64_t now,uint64_t start,uint64_t kickoff) {
    if (now<start) return true;
    return now-start>=30000 || (kickoff && now>=kickoff && now-kickoff>=8000);
}
