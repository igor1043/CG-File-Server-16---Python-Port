#pragma once
#include <math.h>
#include "mascot_walk_clips.h"
#include "mascot_goal_clip.h"
#include "mascot_goal_jump_clip.h"
#include "mascot_goal_fists_clip.h"
#include "mascot_goal_jump_fists_clip.h"
#include "mascot_goal_bounce_clip.h"
#include "mascot_goal_arms_clip.h"

struct MascotStandingClip {
    const float* frames;
    const float* times;
    const float* lift;
    unsigned int count;
    float duration;
    int nativeClip;
    const char* name;
};
static const MascotStandingClip mascotGoalClips[]={
    {&mascotGoalFrames[0][0],mascotGoalTimes,mascotGoalLift,mascotGoalFrameCount,mascotGoalDuration,108,"raised_arms"},
    {&mascotGoalJumpFrames[0][0],mascotGoalJumpTimes,mascotGoalJumpLift,mascotGoalJumpFrameCount,mascotGoalJumpDuration,112,"jump"},
    {&mascotGoalFistsFrames[0][0],mascotGoalFistsTimes,mascotGoalFistsLift,mascotGoalFistsFrameCount,mascotGoalFistsDuration,129,"wide_arm_gesture"},
    {&mascotGoalJumpFistsFrames[0][0],mascotGoalJumpFistsTimes,mascotGoalJumpFistsLift,mascotGoalJumpFistsFrameCount,mascotGoalJumpFistsDuration,117,"jump_fists"},
    {&mascotGoalBounceFrames[0][0],mascotGoalBounceTimes,mascotGoalBounceLift,mascotGoalBounceFrameCount,mascotGoalBounceDuration,118,"bounce"},
    {&mascotGoalArmsFrames[0][0],mascotGoalArmsTimes,mascotGoalArmsLift,mascotGoalArmsFrameCount,mascotGoalArmsDuration,121,"arm_cheer"}
};
static constexpr unsigned int mascotGoalClipCount=sizeof(mascotGoalClips)/sizeof(mascotGoalClips[0]);
static const MascotStandingClip mascotSupportClips[]={
    {&mascotCheerFrames[0][0],mascotCheerTimes,nullptr,mascotCheerFrameCount,mascotCheerDuration,109,"applause"},
    {&mascotGoalFistsFrames[0][0],mascotGoalFistsTimes,nullptr,mascotGoalFistsFrameCount,mascotGoalFistsDuration,129,"wide_arm_support"},
    {&mascotGoalFrames[0][0],mascotGoalTimes,nullptr,mascotGoalFrameCount,mascotGoalDuration,108,"raised_arm_support"}
};
static constexpr unsigned int mascotSupportClipCount=sizeof(mascotSupportClips)/sizeof(mascotSupportClips[0]);

// Deterministic selection: replaying the same event/time selects the same clip.
// Play several native reactions in succession instead of looping only one.
static unsigned int mascot_goal_sequence(unsigned int event,float elapsed,float& phase) {
    unsigned int index=event%mascotGoalClipCount;
    float remaining=fmaxf(0,elapsed);
    float cycle=0;for(const auto& clip:mascotGoalClips)cycle+=clip.duration;
    remaining=fmodf(remaining,cycle);
    for(unsigned int i=0;i<mascotGoalClipCount;++i) {
        if(remaining<mascotGoalClips[index].duration)break;
        remaining-=mascotGoalClips[index].duration;index=(index+1)%mascotGoalClipCount;
    }
    phase=remaining;return index;
}
static float mascot_clip_lift(const MascotStandingClip& clip,float phase) {
    if(!clip.lift || clip.count<2)return 0;
    phase=fmodf(fmaxf(0,phase),clip.duration);
    unsigned int hi=1;while(hi+1<clip.count && clip.times[hi]<phase)++hi;
    const unsigned int lo=hi-1;
    const float span=clip.times[hi]-clip.times[lo];
    const float alpha=span>1e-6f?fmaxf(0,fminf(1,(phase-clip.times[lo])/span)):0;
    return clip.lift[lo]+(clip.lift[hi]-clip.lift[lo])*alpha;
}
