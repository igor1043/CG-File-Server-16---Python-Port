#include "palette.h"
#include <assert.h>
int main() {
    const auto* cor=pyro_palette(1041);
    assert(cor && cor->primary[0]==255 && cor->primary[1]==255 && cor->primary[2]==255);
    assert(cor->secondary[0]==0 && cor->secondary[1]==0 && cor->secondary[2]==0);
    const auto* fla=pyro_palette(1043);assert(fla && fla->primary[0]==215 && fla->primary[1]==0);
    const auto* mir=pyro_palette(113163);assert(mir && mir->primary[0]==253 && mir->secondary[1]==128);
    float c[4]={};pyro_palette_rgb(cor->primary,0.95f,true,c);
    assert(c[0]==1 && c[1]==1 && c[2]==1 && c[3]==0.95f);
    pyro_palette_rgb(cor->secondary,1,false,c);assert(c[0]==0.035f && c[3]==1);
    assert(!pyro_palette(0) && !pyro_palette(999999));
    const size_t count=sizeof(teamPalettes)/sizeof(teamPalettes[0]);
    for(size_t i=0;i<count;++i) {
        assert(pyro_palette(teamPalettes[i].team)==teamPalettes+i);
        if(i)assert(teamPalettes[i-1].team<teamPalettes[i].team);
    }
    assert(pyro_attribute_hash("vColorMult",pyro_attribute_hash("PclSys/stadium_pyrotechnics/smoke_base/ParticleActionRender"))==pyro_attribute_hash("PclSys/stadium_pyrotechnics/smoke_base/ParticleActionRendervColorMult"));
}
