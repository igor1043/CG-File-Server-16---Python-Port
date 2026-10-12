#pragma once
#include <math.h>

static float mascot_wrap_heading(float value) {
    return atan2f(sinf(value),cosf(value));
}
static float mascot_turn_heading(float yaw,float target,float dt) {
    const float delta=mascot_wrap_heading(target-yaw);
    const float step=fmaxf(0,dt)*2.4f;
    return mascot_wrap_heading(yaw+fmaxf(-step,fminf(step,delta)));
}
// Local model forward is +Z. The foot moving backwards is in stance;
// its displacement is the actor's root advance, measured after retarget.
static float mascot_contact_advance(const float before[2][3],const float after[2][3]) {
    return fmaxf(0,fmaxf(before[0][2]-after[0][2],before[1][2]-after[1][2]));
}
