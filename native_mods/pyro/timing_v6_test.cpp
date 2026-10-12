#include "timing_v6.h"
#include <assert.h>
int main() {
    // Intro-only sequence cannot exceed 30 s.
    assert(!pyro_expired(39999,10000,0));
    assert(pyro_expired(40000,10000,0));
    // Early kickoff ends at 8 s afterward, within total cap.
    assert(!pyro_expired(22999,10000,15000));
    assert(pyro_expired(23000,10000,15000));
    // Late kickoff never extends an intro beyond the cap.
    assert(pyro_expired(40000,10000,39000));
    // Manual start during gameplay gets only 8 s.
    assert(!pyro_expired(17999,10000,10000));
    assert(pyro_expired(18000,10000,10000));
    // Clock rollback fails closed.
    assert(pyro_expired(9999,10000,0));
}
