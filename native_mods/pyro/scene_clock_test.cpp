#include "scene_clock.h"
#include "timing_v14.h"
#include "ending.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
static PyroSceneSample frame(uint64_t time,bool replay=false,uintptr_t source=1) {
    return {source,time,true,replay};
}
int main() {
    PyroSceneClock clock;
    clock.begin(frame(30),10000);
    clock.advance(frame(90),11000,false);
    assert(clock.elapsed==1000);
    // Native time can freeze or use a different scale without extending a show.
    clock.advance(frame(90),12000,false);
    assert(clock.elapsed==2000);
    clock.advance({},13000,false);
    assert(clock.elapsed==3000);
    clock.advance(frame(1,false,2),14000,false);
    assert(clock.elapsed==4000);
    clock.advance(frame(2,false,2),14100,true); // explicit pause or metadata gap
    clock.advance(frame(3,false,2),72000,true);
    clock.advance(frame(4,false,2),72500,false);
    assert(clock.elapsed==4000); // no catch-up across an explicitly held interval
    clock.advance(frame(5,false,2),72700,false);
    assert(clock.elapsed==4200);
    clock.advance(frame(100,true),73000,false);
    clock.advance(frame(30000,true),103000,false);
    clock.advance(frame(2000),103100,false);
    assert(clock.elapsed==4200); // replay seek and return cannot expire the show
    clock.advance(frame(2300),103400,false);
    assert(clock.elapsed==4500);
    for(bool goal:{false,true}) {
        const uint64_t duration=goal?25000:60000;
        for(uint64_t unitsPerSecond:{0ULL,60ULL,1000ULL,1000000ULL}) {
            PyroSceneClock bounded;
            bounded.begin(frame(0),10000);
            bounded.advance(frame((duration-1)*unitsPerSecond/1000),10000+duration-1,false);
            assert(bounded.elapsed==duration-1 && !pyro_show_expired(bounded.elapsed,0,goal));
            assert(pyro_drain_due(bounded.elapsed,0,goal,0));
            bounded.advance(frame(duration*unitsPerSecond/1000),10000+duration,false);
            assert(bounded.elapsed==duration && pyro_show_expired(bounded.elapsed,0,goal));
        }
    }

    PyroSceneRestart restart;
    assert(!restart.sample(frame(3000),true,true,1000));
    assert(!restart.sample(frame(100),true,true,2000));
    assert(!restart.sample(frame(500),true,true,2400));
    assert(restart.sample(frame(600),true,true,2500));
    assert(!restart.sample(frame(700),true,true,2600));
    // Repeated restart at 0:0, before kickoff, with reused native objects.
    assert(!restart.sample(frame(1500),true,true,3000));
    assert(!restart.sample(frame(50),true,true,3100));
    assert(restart.sample(frame(550),true,true,3600));
    assert(!restart.sample(frame(100,true),false,true,4000));
    assert(!restart.sample(frame(2000,true),false,true,5000));
    assert(!restart.sample(frame(600),true,true,5100));
    assert(!restart.sample(frame(900),true,true,5700));
    assert(!restart.sample(frame(50),false,true,6000)); // named pause/preview
    assert(!restart.sample(frame(500),true,true,6700));
    assert(!restart.sample(frame(2500),true,false,7000));
    assert(!restart.sample(frame(100),true,false,7100)); // scored fixture is not reset
    assert(!restart.sample(frame(800),true,false,7800));
    std::puts("Real 60s/25s bounds independent of native clock units/freeze, held pause/replay and restart: PASS");
}
