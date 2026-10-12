#pragma once
#include <stdint.h>
static bool pyro_team_valid(double id) {
    return id>0 && id<=1000000 && id==(double)(int)id;
}
static uintptr_t pyro_team_key(uintptr_t scene,int home,int away) {
    const uint64_t h=(uint64_t)(unsigned int)home*0x9e3779b185ebca87ULL;
    const uint64_t a=(uint64_t)(unsigned int)away*0xc2b2ae3d27d4eb4fULL;
    return scene ^ (uintptr_t)h ^ (uintptr_t)a;
}
