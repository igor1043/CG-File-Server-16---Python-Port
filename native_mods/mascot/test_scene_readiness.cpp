// Exercise the actual placement-failure path against private local fixtures.
// No game process is opened and no native FIFA function is called.
#include "mascot_goal_line.cpp"
#include <cassert>
static void ignore_selection(void* input){(void)input;}
int main(){
    alignas(16) unsigned char renderer[0x2000]{};
    alignas(16) unsigned char prototypes[4][3][0x20]{};
    alignas(16) unsigned char records[4][3][0x50]{};
    uintptr_t pointers[4][3]{};
    for(unsigned i=0;i<mascotPlacementTypeCount;++i){
        const uint16_t type=(uint16_t)mascotPlacementTypes[i];
        const uint16_t reserved=(uint16_t)mascot_reserved_appearance(type);
        for(uint16_t j=0;j<=reserved;++j){
            std::memcpy(prototypes[i][j]+12,&type,2);
            std::memcpy(prototypes[i][j]+14,&j,2);
            pointers[i][j]=(uintptr_t)prototypes[i][j];
        }
        const uintptr_t p=(uintptr_t)pointers[i],r=(uintptr_t)records[i];
        const uintptr_t pv[3]={p,p+(reserved+1)*8,p+(reserved+1)*8};
        const uintptr_t rv[3]={r,r+sizeof(records[i]),r+sizeof(records[i])};
        std::memcpy(renderer+0x30*(type+1),pv,sizeof(pv));
        std::memcpy(renderer+0x30*(type+0x2f),rv,sizeof(rv));
        records[i][1][0x42]=(unsigned char)reserved;
        records[i][0][0x42]=0;
        records[i][0][0x20]=42;
    }
    // One category is not constructed yet. That makes assignment fail, while
    // the other categories still have valid, fresh-owned origin placements.
    const uintptr_t invalid[3]={1,2,2};
    std::memcpy(renderer+0x30*(mascotPlacementTypes[3]+0x2f),invalid,sizeof(invalid));
    originalSelect=ignore_selection;
    selection_hook(renderer);
    for(unsigned i=0;i<3;++i){
        assert(records[i][1][0x42]<mascot_reserved_appearance(mascotPlacementTypes[i]));
        assert(records[i][1][0x40]==0xff&&records[i][1][0x41]==0xff);
        assert(records[i][0][0x42]==0&&records[i][0][0x20]==42);
    }
    // No ownership proof for the fourth vector: it must remain untouched.
    assert(records[3][1][0x42]==mascot_reserved_appearance(mascotPlacementTypes[3]));
    puts("PASS actual selection failure: owned mascot origins hidden, normal actors preserved, invalid vectors untouched");
}
