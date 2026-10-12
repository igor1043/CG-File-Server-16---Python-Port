#include "lifecycle_v17.h"
#include "goal_v11.h"
#include <assert.h>
int main() {
    PyroLifecycle life;
    assert(!life.sample(true,0,0,0,false,100));
    assert(!life.sample(true,30000,1,0,false,1000));
    // Reset with the SAME match pointer, followed by another goal.
    assert(!life.sample(true,0,0,0,false,2000));
    assert(!life.sample(true,30,0,0,false,2499));
    assert(life.sample(true,50,0,0,false,2500));
    assert(!life.sample(true,50,0,0,false,3000));
    PyroGoals goals;
    assert(!goals.update(3000,0,0,0));assert(!goals.update(3100,1,0,0));
    assert(goals.update(3200,1,0,0));
    // Reset at 0:0 must work too; a replay rewind must not reset the session.
    PyroLifecycle zero;
    assert(!zero.sample(true,20000,0,0,false,100));
    assert(!zero.sample(true,0,0,0,true,1000));assert(!zero.sample(true,0,0,0,true,1600));
    assert(!zero.sample(true,0,0,0,false,2000));assert(zero.sample(true,0,0,0,false,2500));
    PyroLifecycle transient;
    assert(!transient.sample(true,5000,0,0,false,100));
    assert(!transient.sample(true,0,0,0,false,200));
    assert(!transient.sample(true,5001,0,0,false,600));
    assert(!transient.sample(true,2000,0,0,false,1000)); // half-time need not reset
    // Restart before the clock has advanced: retain the reload evidence across samples.
    PyroLifecycle early;
    assert(!early.sample(true,0,0,0,false,100));
    assert(!early.sample(false,0,0,0,false,200));
    assert(!early.sample(true,0,0,0,false,1800));
    assert(early.sample(true,0,0,0,false,2300));
    assert(!early.sample(true,0,0,0,false,2800));
    assert(!early.sample(false,0,0,0,false,3000));
    assert(!early.sample(true,0,0,0,false,4600));
    assert(early.sample(true,0,0,0,false,5100));
    PyroLifecycle immediateGoal;
    assert(!immediateGoal.sample(true,500,1,0,false,100));
    assert(!immediateGoal.sample(true,0,0,0,false,200));
    assert(immediateGoal.sample(true,0,0,0,false,700));
    PyroLifecycle earlyZero;
    assert(!earlyZero.sample(true,200,0,0,false,100));
    assert(!earlyZero.sample(true,0,0,0,false,200));
    assert(earlyZero.sample(true,0,0,0,false,700));
    // The old high-water score suppressed the same goal after Restart.
    PyroGoals retained;
    assert(!retained.update(100,0,0,0));
    assert(!retained.update(200,1,0,0));assert(retained.update(300,1,0,0));
    assert(!retained.update(400,0,0,0));assert(!retained.update(500,0,0,0));
    assert(!retained.update(600,1,0,0));assert(!retained.update(700,1,0,0));
    retained=PyroGoals{};
    assert(!retained.update(800,0,0,0));
    assert(!retained.update(900,1,0,0));assert(retained.update(1000,1,0,0));
}
