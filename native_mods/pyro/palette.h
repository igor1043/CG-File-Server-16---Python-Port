#pragma once
#include <stdint.h>
#include <stddef.h>
struct TeamPalette {int team;unsigned char primary[3],secondary[3];};
#include "team_palettes.h"
static const TeamPalette* pyro_palette(int home) {
    size_t low=0,high=sizeof(teamPalettes)/sizeof(teamPalettes[0]);
    while(low<high) {
        const size_t middle=low+(high-low)/2;
        if(teamPalettes[middle].team<home)low=middle+1;else high=middle;
    }
    return low<sizeof(teamPalettes)/sizeof(teamPalettes[0]) && teamPalettes[low].team==home?teamPalettes+low:nullptr;
}
// Mirror the game's FNV-1 case-sensitive attribute key; parent and leaf concatenate.
static uint32_t pyro_attribute_hash(const char* s,uint32_t h=0x811c9dc5U) {
    for(;*s;++s)h=(h*0x1000193U)^(unsigned char)*s;
    return h;
}
static void pyro_palette_rgb(const unsigned char* rgb,float alpha,bool smoke,float (&out)[4]) {
    const bool black=rgb[0]==0 && rgb[1]==0 && rgb[2]==0;
    for(int i=0;i<3;++i)out[i]=black?(smoke?0.055f:0.035f):(float)rgb[i]/255.0f;
    out[3]=alpha;
}
