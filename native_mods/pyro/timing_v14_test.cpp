#include "timing_v14.h"
#include <assert.h>
int main() {
    assert(!pyro_show_expired(69999,10000,false));
    assert(pyro_show_expired(70000,10000,false));
    assert(!pyro_show_expired(34999,10000,true));
    assert(pyro_show_expired(35000,10000,true));
    assert(pyro_show_expired(9999,10000,false));
    assert(pyro_show_expired(9999,10000,true));
}
