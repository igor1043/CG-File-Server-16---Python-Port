#include "timing_v14.h"
#include <assert.h>
int main() {
    assert(!pyro_show_expired(69999,10000,false));
    assert(pyro_show_expired(70000,10000,false));
    assert(!pyro_show_expired(34999,10000,true));
    assert(pyro_show_expired(35000,10000,true));
    assert(pyro_show_expired(9999,10000,false));
    assert(pyro_show_expired(9999,10000,true));
    uint64_t start=1000;
    PyroShowPause pause;
    assert(!pause.resume(2000,start));
    assert(pause.enter(6000)); // Five seconds into the home-goal show.
    assert(!pause.enter(7000));
    assert(pause.resume(66000,start)); // One minute in pause/replay.
    assert(start==61000);
    assert(!pyro_show_expired(85999,start,true));
    assert(pyro_show_expired(86000,start,true));
    assert(!pause.resume(87000,start));
    assert(pause.enter(88000));
    pause=PyroShowPause{}; // Cleanup, restart or a new event discards old pause.
    start=90000;
    assert(!pause.resume(91000,start) && start==90000);
}
