#include "ending.h"
#include "timing_v14.h"
#include <assert.h>
#include <initializer_list>
int main() {
    static_assert(pyroIntroCount==20 && pyroGoalCount==12,"Every machine has an event source");
    const uint64_t start=1000;
    for(bool goal : {false,true}) {
        const int count=goal?pyroGoalCount:pyroIntroCount;
        const uint64_t length=goal?25000ULL:60000ULL;
        uint64_t previous=0;
        for(int i=0;i<count;i+=2) {
            const uint64_t due=length-12000ULL+(uint64_t)(i/2)*5000ULL/(uint64_t)(count/2-1);
            assert(!pyro_drain_due(start+due-1,start,goal,i));
            assert(pyro_drain_due(start+due,start,goal,i));
            assert(pyro_drain_due(start+due,start,goal,i+1));
            assert(due>=previous && due+6500ULL<length);
            previous=due;
        }
        assert(previous==length-7000ULL);
        assert(!pyro_show_expired(start+length-1,start,goal));
        assert(pyro_show_expired(start+length,start,goal));
        assert(!pyro_drain_due(start-1,start,goal,0));
        assert(!pyro_drain_due(start+length,start,goal,count));
    }
    for(int i=0;i<pyroGoalCount;++i){
        const auto& rear=pyro_site(true,i);
        assert(rear.x==-5900 || rear.x==5900);
        assert(&rear==&machineSites[i+pyroSidelineCount]);
    }
    assert(machineOutletHeightCm>55 && machineOutletHeightCm<60);
}
