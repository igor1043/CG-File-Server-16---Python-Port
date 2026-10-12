#include "goal_v8.h"
#include <assert.h>
int main() {
    PyroGoals g;
    assert(!g.update(0,0,0,0));assert(!g.update(100,1,0,0));
    assert(!g.update(849,1,0,0));assert(g.update(850,1,0,0));
    assert(!g.update(900,1,0,0));
    // Replay score regression and return cannot celebrate the same goal twice.
    assert(!g.update(1000,0,0,0));assert(!g.update(1750,0,0,0));
    assert(!g.update(1800,1,0,0));assert(!g.update(2550,1,0,0));
    assert(!g.update(2600,1,1,0));assert(!g.update(3350,1,1,0));
    assert(!g.update(3400,2,1,0));assert(g.update(4150,2,1,0));
    PyroGoals away;
    assert(!away.update(0,2,2,1));assert(!away.update(100,2,3,1));
    assert(away.update(850,2,3,1));
    PyroGoals transient;
    assert(!transient.update(0,0,0,0));assert(!transient.update(100,1,0,0));
    assert(!transient.update(400,0,0,0));assert(!transient.update(1000,0,0,0));
    assert(!transient.update(1100,4,0,0));assert(!transient.update(1850,4,0,0));
}
