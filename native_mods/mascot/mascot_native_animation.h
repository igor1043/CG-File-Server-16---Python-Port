#pragma once
#include <limits.h>
#include <math.h>
#include "mascot_match_lifecycle.h"
#include "mascot_walk_clips.h"
#include "mascot_animation_variants.h"

// Approved standing clips and foot-driven locomotion use private SLE slot 73.
// CrowdAI is read only for the pause clock. Selected native goal reactions
// are baked offline; replay uses the native time and our recorded palettes.
static volatile LONG mascotAnimationEnabled;
static volatile LONG mascotAnimationHome = -1;
static volatile LONG mascotSceneGeneration;
static volatile LONG mascotPlacementSession;
static volatile LONG mascotAnimationMode;      // 0 inactive, 2 standing idle/walk, 3 home-goal cheer
static volatile LONG mascotGoalEventSerial;
static volatile LONG64 mascotAnimationClockMs;
static bool mascotAnimationInitialized;
static bool mascotAnimationBound;
static uint16_t mascotPreviousBinding = 3;
static uintptr_t mascotAnimatedRenderer, mascotAnimatedRecords;
static size_t mascotAnimatedIndex;
static int mascotAnimatedStadium = -1, mascotAnimatedLight = -1, mascotAnimatedCold = -1;
static unsigned int mascotPrivateSlot = 73;
static unsigned int mascotAnimatedGeneration;
static uintptr_t mascotInitAttemptRenderer, mascotInitAttemptRecords;
static size_t mascotInitAttemptIndex;
static unsigned int mascotInitAttemptGeneration;
static DWORD mascotInitAttemptTick;
static float mascotBindPose[31][16];
static float mascotLastPose[31][16];
struct MascotNativeClock {
    uintptr_t provider=0, crowd=0;
    unsigned int generation=0;
    uint64_t sampleTick=0, lastFrameTick=0, lastChangedTick=0;
    bool hasSample=false;
    unsigned char posture=0;
    int behavior=-1, clip=-1;
    float sample[31][16]{};
};
static MascotNativeClock mascotNativeClock;
#include "mascot_walk_runtime.h"
#include "mascot_replay_clock.h"
#include "mascot_replay_history.h"
static MascotReplayHistory mascotReplayHistory;
static bool mascotWasInReplay=false;
static double mascotLastNativeTime=-1;
static uintptr_t mascotLastNativeSource=0;
static uint64_t mascotLastNativeAdvance=0;

static void mascot_set_animation_active(bool enabled, int home)
{
    const LONG next = enabled ? 1 : 0;
    const LONG previous = InterlockedExchange(&mascotAnimationEnabled, next);
    const LONG oldHome = InterlockedExchange(&mascotAnimationHome, home);
    if (previous != next || oldHome != home) {
        InterlockedIncrement(&mascotSceneGeneration);
        if (!enabled) {
            InterlockedExchange(&mascotAnimationMode, 0);
        }
    }
}

static uintptr_t mascot_current_crowd()
{
    uintptr_t manager, world, game, registry, vt, pairs;
    int key, count;
    if (!get(image + 0x3517420, manager) || !get(manager, vt) || vt != image + 0x2226730 ||
        !get(manager + 8, world) || !get(world, vt) || vt != image + 0x2225d90 ||
        !get(world + 0x10, game) || !get(game, vt) || vt != image + 0x2309370 ||
        !get(game + 0x20, registry) || !registry ||
        !get(registry + 8 + 81 * 32, key) || key != 81 ||
        !get(registry + 8 + 81 * 32 + 16, count) || count < 1 || count > 8 ||
        !get(registry + 8 + 81 * 32 + 24, pairs) || !readable(pairs, (size_t)count * 16)) return 0;
    for (int i = 0; i < count; ++i) {
        uintptr_t object, self, callback;
        if (!get(pairs + i * 16 + 8, object) || !object ||
            !get(object + 0x2918, self) || self != object ||
            !get(object + 0x28e8, callback) || callback != image + 0x2312f88) continue;
        return object;
    }
    return 0;
}

static uintptr_t mascot_cached_crowd(uint64_t now)
{
    static uintptr_t cached=0;
    static uint64_t refreshed=0;
    static unsigned int generation=0;
    if(generation!=mascotPlacementGeneration) {
        cached=0;refreshed=0;generation=mascotPlacementGeneration;
    }
    if(!cached || now-refreshed>=250 || !readable(cached+0x470,sizeof(int))) {
        cached=mascot_current_crowd();
        refreshed=now;
    }
    return cached;
}

static uintptr_t mascot_native_pose_provider()
{
    uintptr_t wrapper,data,manager,impl,provider;
    if(!get(image+0x3504750,wrapper) || !get(wrapper+0x10,data) ||
       !get(data+0x90,manager) || !get(manager,impl) || !get(impl+0x28,provider)) return 0;
    return provider;
}

// The crowd pose provider advances on FIFA's animation clock. Use its motion
// as the clock for mascot locomotion, so a paused replay freezes the route too.
static float mascot_native_animation_dt(uintptr_t crowd,uint64_t now,bool allowAdvance=true)
{
    MascotNativeClock& clock=mascotNativeClock;
    if(clock.crowd!=crowd || clock.generation!=mascotPlacementGeneration) {
        clock={};clock.crowd=crowd;clock.generation=mascotPlacementGeneration;
    }
    if(!crowd) { clock.lastFrameTick=now; return 0; }
    if(!clock.lastFrameTick) clock.lastFrameTick=now;
    uintptr_t provider=clock.provider;
    if(!provider || !clock.sampleTick || now-clock.sampleTick>=50) {
        provider=mascot_native_pose_provider();
    }
    if(!provider || !readable(provider+0x10,31*64)) { clock.provider=0;clock.hasSample=false;clock.lastChangedTick=0;clock.lastFrameTick=now;return 0; }
    if(provider!=clock.provider) { clock.provider=provider;clock.hasSample=false;clock.lastChangedTick=0;clock.sampleTick=0; }
    if(!clock.sampleTick || now-clock.sampleTick>=50) {
        float current[31][16],stable[31][16];
        unsigned char posture,postureAgain;
        int behavior,behaviorAgain,clip,clipAgain;
        const bool hadSample=clock.hasSample;
        clock.hasSample=false;
        if(!get(crowd+12,posture) || !get(crowd+0x474,behavior) || !get(crowd+0x470,clip)) {
            clock.lastChangedTick=0;clock.lastFrameTick=now;return 0;
        }
        memcpy(current,(void*)(provider+0x10),sizeof(current)); MemoryBarrier();
        memcpy(stable,(void*)(provider+0x10),sizeof(stable));
        clock.sampleTick=now;
        if(memcmp(current,stable,sizeof(current)) ||
           !get(crowd+12,postureAgain) || posture!=postureAgain ||
           !get(crowd+0x474,behaviorAgain) || behavior!=behaviorAgain ||
           !get(crowd+0x470,clipAgain) || clip!=clipAgain) {
            clock.lastChangedTick=0;clock.lastFrameTick=now;return 0;
        }
        for(size_t bone=0;bone<31;++bone) {
            for(size_t j=0;j<16;++j) if(!isfinite(current[bone][j]) || fabsf(current[bone][j])>1000) {
                clock.lastChangedTick=0;clock.lastFrameTick=now;return 0;
            }
            if(fabsf(current[bone][15]-1)>0.001f) {
                clock.lastChangedTick=0;clock.lastFrameTick=now;return 0;
            }
        }
        // sampleTick is reset when the source changes. Never compare poses
        // from different scene objects to manufacture an animation tick.
        if(hadSample && memcmp(current,clock.sample,sizeof(current))) clock.lastChangedTick=now;
        memcpy(clock.sample,current,sizeof(current));clock.hasSample=true;
        clock.posture=posture;clock.behavior=behavior;clock.clip=clip;
    }
    float dt=(float)(now-clock.lastFrameTick)*.001f;
    clock.lastFrameTick=now;
    if(dt<0 || dt>.05f) dt=.05f;
    if(!clock.lastChangedTick || now-clock.lastChangedTick>250) dt=0;
    if(!allowAdvance)dt=0;
    if(dt>0) InterlockedExchangeAdd64(&mascotAnimationClockMs,(LONG64)(dt*1000.0f));
    return dt;
}

static uint64_t mascot_animation_clock_now()
{
    const LONG64 value=InterlockedCompareExchange64(&mascotAnimationClockMs,0,0);
    return value>0?(uint64_t)value:0;
}

static bool mascot_read_confirmed_score(uintptr_t& matchKey, int& homeClub, int& awayClub,
                                        int& homeScore, int& awayScore, bool sceneGenerationKey=true)
{
    uintptr_t manager, world, game, registry, vt, pairs;
    int key, count;
    if (!get(image + 0x3517420, manager) || !get(manager, vt) || vt != image + 0x2226730 ||
        !get(manager + 8, world) || !get(world, vt) || vt != image + 0x2225d90 ||
        !get(world + 0x10, game) || !get(game, vt) || vt != image + 0x2309370 ||
        !get(game + 0x20, registry) || !registry ||
        !get(registry + 8 + 15 * 32, key) || key != 15 ||
        !get(registry + 8 + 15 * 32 + 16, count) || count != 2 ||
        !get(registry + 8 + 15 * 32 + 24, pairs) || !readable(pairs, 32)) return false;
    uintptr_t team[2]{};
    int club[2] = {-1, -1};
    for (int i = 0; i < 2; ++i) {
        uintptr_t candidate, stats;
        int side;
        if (!get(pairs + i * 16 + 8, candidate) || !candidate ||
            !get(candidate, vt) || vt != image + 0x22fe9f0 ||
            !get(candidate + 0x30, manager) || manager != registry ||
            !get(candidate + 0x58, side) || side < 0 || side > 1 || team[side] ||
            !get(candidate + 0x50, stats) || !get(stats + 0x80, club[side]) ||
            club[side] <= 0 || club[side] > 1000000) return false;
        team[side] = candidate;
    }
    uintptr_t cache, cacheVtable, getter, rows, homeCallback, awayCallback, again;
    int h, a, h2, a2;
    if (!get(image + 0x34a30b0, cache) || !cache || !get(cache, cacheVtable) ||
        cacheVtable != image + 0x21141f0 || !get(cacheVtable + 16, getter) ||
        getter != image + 0x3acbff0 || !get(cache + 8, rows) || !readable(rows, 249 * 16) ||
        !get(rows + 21 * 16 + 8, homeCallback) || !get(rows + 6 * 16 + 8, awayCallback) ||
        homeCallback != image + 0x3acc040 || awayCallback != image + 0x3acc040 ||
        !get(rows + 21 * 16, h) || !get(rows + 6 * 16, a) ||
        !get(rows + 21 * 16, h2) || !get(rows + 6 * 16, a2) ||
        h != h2 || a != a2 || h < 0 || h > 99 || a < 0 || a > 99 ||
        !get(cache + 8, again) || again != rows ||
        !get(image + 0x34a30b0, again) || again != cache) return false;
    homeClub = club[0]; awayClub = club[1]; homeScore = h; awayScore = a;
    const uintptr_t generation = (uintptr_t)(unsigned int)InterlockedCompareExchange(&mascotSceneGeneration, 0, 0);
    matchKey = rows ^ team[0] ^ (team[1] << 11 | team[1] >> (sizeof(uintptr_t) * 8 - 11)) ^
        (sceneGenerationKey ? generation * (uintptr_t)0x9e3779b97f4a7c15ULL : 0);
    return matchKey != 0;
}

static bool mascot_invert_affine(const float* matrix, float* output)
{
    for (size_t i = 0; i < 16; ++i) if (!isfinite(matrix[i]) || fabsf(matrix[i]) > 20000) return false;
    if (fabsf(matrix[15] - 1) > 0.001f) return false;
    const float a=matrix[0], b=matrix[4], c=matrix[8], d=matrix[1], e=matrix[5], f=matrix[9],
                g=matrix[2], h=matrix[6], i=matrix[10];
    const float determinant=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g);
    if (!isfinite(determinant) || fabsf(determinant) < 0.0001f) return false;
    memset(output, 0, 16 * sizeof(float)); output[15]=1;
    const float rows[9]={e*i-f*h,c*h-b*i,b*f-c*e,f*g-d*i,a*i-c*g,c*d-a*f,d*h-e*g,b*g-a*h,a*e-b*d};
    for (size_t row=0;row<3;++row) for (size_t column=0;column<3;++column)
        output[column*4+row]=rows[row*3+column]/determinant;
    for (size_t row=0;row<3;++row)
        output[12+row]=-(output[row]*matrix[12]+output[4+row]*matrix[13]+output[8+row]*matrix[14]);
    return true;
}

[[maybe_unused]] static bool mascot_native_standing_pose(uintptr_t crowd,uintptr_t provider,int requested, float pose[31][16], int& behaviorOut, int& clip)
{
    const MascotNativeClock& clock=mascotNativeClock;
    if (!crowd || !provider || !clock.hasSample || crowd!=clock.crowd || provider!=clock.provider ||
        clock.generation!=mascotPlacementGeneration) return false;
    const unsigned char posture = clock.posture;
    const int behavior = clock.behavior;
    /* Keep the mascot standing: seated/non-standing crowd postures are never copied. */
    // Upright geometry alone admits early/late frames of seated clips.
    // Only the extracted standing goal clip is eligible for native copying.
    if (!mascot_goal_pose_allowed(posture,requested,behavior,clock.clip)) return false;
    memcpy(pose,clock.sample,sizeof(clock.sample));
    if (pose[2][13] < 75 || pose[2][13] > 160 || pose[14][13] < 120) return false;
    if(!mascot_pose_upright(pose))return false;
    // Keep the live crowd goal motion, but preserve this mascot's bind lengths.
    // Copying human world positions directly stretches custom heads and arms.
    float source[31*7];
    for(unsigned int bone=0;bone<31;++bone) {
        const unsigned int at=bone*7;
        for(unsigned int axis=0;axis<3;++axis)source[at+axis]=pose[bone][12+axis];
        const MascotWalkQuaternion q=mascot_wq_from_matrix(pose[bone]);
        source[at+3]=q.x;source[at+4]=q.y;source[at+5]=q.z;source[at+6]=q.w;
    }
    mascot_retarget_baked_pose(source,pose);
    behaviorOut = behavior;
    clip = clock.clip;
    return true;
}

static void mascot_unbind_pose(uintptr_t renderer, uintptr_t records, size_t count)
{
    if (mascotAnimationBound && renderer == mascotAnimatedRenderer && records == mascotAnimatedRecords &&
        mascotAnimatedIndex < count && readable(records + mascotAnimatedIndex * 0x50, 0x50)) {
        uint16_t binding;
        if (get(mascotAnimatedRecords + mascotAnimatedIndex * 0x50 + 0x40, binding) && binding == mascotPrivateSlot)
            *(uint16_t*)(mascotAnimatedRecords + mascotAnimatedIndex * 0x50 + 0x40) = mascotPreviousBinding;
    }
    mascotAnimationBound = false; mascotAnimationInitialized = false;
}

static void mascot_animate_instance(const MascotFrameContext& frame)
{
    const uintptr_t renderer=frame.renderer, records=frame.records;
    const size_t count=frame.count, selected=frame.selected;
    const int home=frame.home, stadium=frame.stadium, light=frame.light, cold=frame.cold;
    const bool animatedPackage=frame.packageAnimated;
    if(!frame.mascotActive || !animatedPackage) {
        mascot_unbind_pose(renderer,records,count); mascot_set_animation_active(false,home); return;
    }
    if(!mascotAnimationInitialized || renderer!=mascotAnimatedRenderer || records!=mascotAnimatedRecords ||
        selected!=mascotAnimatedIndex || stadium!=mascotAnimatedStadium || light!=mascotAnimatedLight || cold!=mascotAnimatedCold ||
        frame.generation!=mascotAnimatedGeneration) {
        const DWORD tick=GetTickCount();
        const bool sameAttempt=renderer==mascotInitAttemptRenderer && records==mascotInitAttemptRecords &&
            selected==mascotInitAttemptIndex && frame.generation==mascotInitAttemptGeneration;
        if (sameAttempt && tick-mascotInitAttemptTick<250) return;
        mascotInitAttemptRenderer=renderer; mascotInitAttemptRecords=records;
        mascotInitAttemptIndex=selected; mascotInitAttemptGeneration=frame.generation; mascotInitAttemptTick=tick;
        uint16_t incomingBinding=0;unsigned char incomingAppearance=0;
        const bool ownsIncomingSlot=get(records+selected*0x50+0x40,incomingBinding) && incomingBinding==mascotPrivateSlot &&
            get(records+selected*0x50+0x42,incomingAppearance) && incomingAppearance==mascot_reserved_appearance(frame.appearanceType);
        mascot_unbind_pose(renderer,records,count);
        mascot_set_animation_active(false,home);
        wchar_t variant[MAX_PATH];
        const int chars=_snwprintf_s(variant,MAX_PATH,_TRUNCATE,L"%ls\\data\\sceneassets\\mascot\\%u\\model_animated.rx3",gameDirectory,(unsigned int)home);
        if(chars<0 || !mascot_rx3_file_valid(variant,false)) { log_event("animation_fallback invalid_variant club=%d",home); mascot_set_animation_active(false,home); return; }
        for(unsigned int type=0;type<23;++type) {
            uintptr_t begin;size_t n;
            if(!vector_bounds(renderer+0x30*(type+0x2f),0x50,begin,n)) return;
            for(size_t i=0;i<n;++i) if(*(uint16_t*)(begin+i*0x50+0x40)==mascotPrivateSlot && (type!=frame.appearanceType || i!=selected)) return;
        }
        if(*(unsigned char*)(renderer+mascotPrivateSlot*0xe00+0xf5d0)!=0 && !ownsIncomingSlot) {
            static DWORD lastBusyLog=0;
            if(!lastBusyLog || tick-lastBusyLog>=5000){lastBusyLog=tick;log_event("animation_wait club=%d reason=private_slot_occupied placement_type=%u",home,frame.appearanceType);}
            return;
        }
        uintptr_t inverse;
        if(!get(renderer+0x4f440,inverse) || !readable(inverse,sizeof(mascotBindPose))) return;
        float inverseMatrices[31][16];memcpy(inverseMatrices,(void*)inverse,sizeof(inverseMatrices));
        for(size_t bone=0;bone<31;++bone) if(!mascot_invert_affine(inverseMatrices[bone],mascotBindPose[bone])) return;
        mascot_load_foot_markers(home);
        memcpy(mascotLastPose,mascotBindPose,sizeof(mascotLastPose));
        uint16_t previousBinding=3;
        if (!get(records+selected*0x50+0x40,previousBinding) || previousBinding>=74 || previousBinding==mascotPrivateSlot)
            previousBinding=3;
        mascotPreviousBinding=previousBinding;
        mascotAnimatedRenderer=renderer;mascotAnimatedRecords=records;mascotAnimatedIndex=selected;
        mascotAnimatedStadium=stadium;mascotAnimatedLight=light;mascotAnimatedCold=cold;
        mascotAnimatedGeneration=frame.generation;
        mascotAnimationInitialized=true;mascotAnimationBound=false;
        log_event("animation_ready club=%d instance=%zu slot=73 idle=approved_baked goal_variants=6 support_variants=3 contact_walk=1 foot_markers=%u no_sit_pose=1",home,selected+1,(unsigned int)mascotFootMarkersReady);
    }
    mascot_set_animation_active(true,home);
    const LONG mode=InterlockedCompareExchange(&mascotAnimationMode,0,0);
    const uint64_t now=GetTickCount64();
    const MascotReplayClockSample replayClock=mascot_read_replay_clock();
    const LONG session=InterlockedCompareExchange(&mascotPlacementSession,0,0);
    mascotReplayHistory.bind(home,session);
    if(replayClock.valid && replayClock.replay) {
        float pose[31][16],position[3];int kind=0,clip=-1;bool clamped=false;
        const bool recorded=mascotReplayHistory.sample(replayClock.time,position,pose,kind,clip,clamped);
        if(recorded) {
            memcpy((void*)(records+selected*0x50+0x20),position,sizeof(position));
            const float neutral=0;
            memcpy((void*)(records+selected*0x50+0x1c),&neutral,sizeof(neutral));
            memcpy((void*)(records+selected*0x50+0x2c),&neutral,sizeof(neutral));
        } else memcpy(pose,mascotLastPose,sizeof(pose));
        memcpy((void*)(renderer+mascotPrivateSlot*0xe00+0xe7e0),pose,sizeof(pose));
        *(uint16_t*)(records+selected*0x50+0x40)=(uint16_t)mascotPrivateSlot;
        mascotAnimationBound=true;
        static double lastReportedTime=-1;static int lastKind=-1,lastClip=-1;
        if(!mascotWasInReplay || kind!=lastKind || clip!=lastClip || fabs(replayClock.time-lastReportedTime)>5) {
            log_event("replay_pose native_time=%.6f stored=%u recorded=%u clamped=%u kind=%d clip=%d position_z=%.3f",replayClock.time,mascotReplayHistory.count,(unsigned int)recorded,(unsigned int)clamped,kind,clip,recorded?position[2]:targetPosition[2]);
            lastReportedTime=replayClock.time;lastKind=kind;lastClip=clip;
        }
        mascotWasInReplay=true;
        return;
    }
    if(mascotWasInReplay && mascotReplayHistory.count) {
        float position[3],pose[31][16];int kind=0,clip=-1;bool clamped=false;
        if(mascotReplayHistory.sample(mascotReplayHistory.at(mascotReplayHistory.count-1).time,position,pose,kind,clip,clamped))
            memcpy(mascotLastPose,pose,sizeof(pose));
        log_event("replay_finished live_route_preserved=1");
    }
    mascotWasInReplay=false;
    if(mascotWalkRuntime.ready && mascotWalkRuntime.home==home && mascotWalkRuntime.session==session)
        mascotWalkRuntime.generation=frame.generation;
    bool allowAdvance=true;
    if(replayClock.valid) {
        if(replayClock.source!=mascotLastNativeSource || replayClock.time!=mascotLastNativeTime)mascotLastNativeAdvance=now;
        else if(now-mascotLastNativeAdvance>250)allowAdvance=false;
        mascotLastNativeSource=replayClock.source;mascotLastNativeTime=replayClock.time;
    }
    const uintptr_t crowd=mascot_cached_crowd(now);
    const float dt=mascot_native_animation_dt(crowd,now,allowAdvance);
    mascot_walk_update(frame,mode,now,dt);
    MascotWalkRuntime& motion=mascotWalkRuntime;
    const bool waypointInteraction=mascot_waypoint_interaction();
    // Goals must never fall back to the waypoint applause clip. The captured
    // crowd reaction is self-contained even when live crowd slot 0 changes.
    const int poseKind=mode==3?3:(motion.walking?1:(waypointInteraction?2:0));
    float matrices[31][16];
    float phase=motion.clipTime;
    unsigned int variant=0;
    const MascotStandingClip* standing=nullptr;
    if(poseKind==3) {
        variant=mascot_goal_sequence((unsigned int)InterlockedCompareExchange(&mascotGoalEventSerial,0,0),motion.clipTime,phase);
        standing=&mascotGoalClips[variant];
    } else if(poseKind==2) {
        const float interactionElapsed=fmaxf(0,22.5f-motion.idleRemaining);
        const unsigned int segment=interactionElapsed>=7.5f?1u:0u;
        variant=(motion.waypointVisitSerial-1+segment)%mascotSupportClipCount;
        phase=interactionElapsed-(float)segment*7.5f;
        standing=&mascotSupportClips[variant];
    }
    const int behavior=poseKind==3?14:-1;
    const int clip=standing?standing->nativeClip:-1;
    const int blendKind=standing?(poseKind==3?10:20)+(int)variant:poseKind;
    float lift=poseKind==3?mascot_clip_lift(*standing,phase):0;
    {
        float sampled[31*7];
        if(standing) mascot_sample_baked_clip(standing->frames,standing->times,standing->count,standing->duration,phase,sampled);
        else if(poseKind==1) mascot_sample_baked_clip(&mascotWalkFrames[0][0],mascotWalkTimes,mascotWalkFrameCount,mascotWalkDuration,motion.walkTime,sampled);
        else mascot_sample_baked_clip(&mascotIdleFrames[0][0],mascotIdleTimes,mascotIdleFrameCount,mascotIdleDuration,motion.clipTime,sampled);
        mascot_retarget_baked_pose(sampled,matrices);
    }
    // Validate the final retarget as well as native sources. A bad transition
    // cannot become the next fallback pose. Paused frames retain the last pose.
    if(!mascot_pose_upright(matrices) || (dt==0 && motion.hasPose))memcpy(matrices,mascotLastPose,sizeof(matrices));
    else {
        mascot_blend_local_pose(matrices,blendKind,dt);
        mascot_ground_pose(matrices,dt);
        if(motion.transitioning) {
            const float alpha=fminf(1,motion.blendElapsed/.35f);
            lift=motion.liftBlendSource+(lift-motion.liftBlendSource)*alpha;
        }
        motion.visualLift=lift;
        for(unsigned int bone=0;bone<31;++bone)matrices[bone][13]+=lift;
        mascot_orient_pose(matrices,motion.yaw);
    }
    for(size_t bone=0;bone<31;++bone)for(size_t element=0;element<16;++element)
        if(!isfinite(matrices[bone][element])||fabsf(matrices[bone][element])>20000)return;
    memcpy(mascotLastPose,matrices,sizeof(mascotLastPose));
    motion.hasPose=true;
    memcpy((void*)(renderer+mascotPrivateSlot*0xe00+0xe7e0),matrices,sizeof(matrices));
    *(uint16_t*)(records+selected*0x50+0x40)=(uint16_t)mascotPrivateSlot;
    mascotAnimationBound=true;
    if(replayClock.valid)
        mascotReplayHistory.record(replayClock.time,now,motion.position,matrices,poseKind,clip);
    static int lastPoseKind=-1,lastVariant=-1;
    if(lastPoseKind!=poseKind || lastVariant!=(int)variant) {
        const char* source=poseKind==3?"captured_crowd_home_goal":poseKind==1?"contact_walk":poseKind==2?"captured_waypoint_support":"approved_standing_idle";
        log_event("animation_pose club=%d kind=%s source=%s behavior=%d clip=%d variant=%s lift_cm=%.3f engine_dt=%.3f no_sit=1",home,poseKind==3?"home_goal":poseKind==2?"waypoint_interaction":poseKind==1?"walk":"idle",source,behavior,clip,standing?standing->name:"none",lift,dt);
        lastPoseKind=poseKind;lastVariant=(int)variant;
    }
}

static DWORD WINAPI mascot_animation_worker(void*)
{
    MascotMatchLifecycle matchLifecycle;
    bool baseline=false, candidate=false, previousActive=false;
    uintptr_t currentKey=0;
    int scoreHome=-1,scoreAway=-1,candidateHome=-1,candidateAway=-1,highHome=-1;
    uint64_t candidateSince=0,lastSample=0,celebrationUntilEngine=0;
    for(unsigned attempt=0;attempt<600;++attempt) {
        if(!code_ready()) { Sleep(200);continue; }
        break;
    }
    if(!code_ready()) { log_event("animation_disabled code_guard_failed"); return 1; }
    log_event("animation_score_watcher started home_only=1 confirm_ms=750 crowd_read_only=1 crowd_hook=0 captured_goal_variants=6 support_variants=3 replay_clock_read_only=1 waypoint_applause_separate=1 no_sit_pose=1 duration_engine_ms=15000");
    for(;;) {
        const uint64_t now=GetTickCount64();
        const auto replayClock=mascot_read_replay_clock();
        if(replayClock.valid && replayClock.replay) { lastSample=0;Sleep(100);continue; }
        const bool active=InterlockedCompareExchange(&mascotAnimationEnabled,0,0)!=0;
        const int mascotClub=InterlockedCompareExchange(&mascotAnimationHome,0,0);
        if(!active || mascotClub<=0) {
            if(previousActive) {
                InterlockedExchange(&mascotAnimationMode,0);
                log_event("animation_idle no_supported_home_mascot");
            }
            previousActive=false;baseline=candidate=false;currentKey=0;celebrationUntilEngine=0;lastSample=0;
            Sleep(100);continue;
        }
        if(!previousActive) {
            InterlockedExchange(&mascotAnimationMode,2);
        }
        previousActive=true;
        uintptr_t key=0;int homeClub=-1,awayClub=-1,h=-1,a=-1;
        if(!mascot_read_confirmed_score(key,homeClub,awayClub,h,a,false) || homeClub!=mascotClub) {
            (void)matchLifecycle.sample(false,0,0,0,now);
            InterlockedExchange(&mascotAnimationMode,2);
            baseline=candidate=false;lastSample=0;Sleep(100);continue;
        }
        const int sessionReason=matchLifecycle.sample(true,key,h,a,now);
        if(sessionReason){
            const LONG session=InterlockedIncrement(&mascotPlacementSession);
            baseline=candidate=false;celebrationUntilEngine=0;lastSample=0;
            InterlockedExchange(&mascotAnimationMode,2);
            log_event("match_session_confirmed session=%ld reason=%d native_key=%p score=%d:%d",session,sessionReason,(void*)key,h,a);
        }
        key ^= (uintptr_t)(unsigned int)InterlockedCompareExchange(&mascotSceneGeneration,0,0)*(uintptr_t)0x9e3779b97f4a7c15ULL;
        key ^= (uintptr_t)(unsigned int)homeClub << 3;
        key ^= (uintptr_t)(unsigned int)awayClub << 29;
        if(key!=currentKey) {
            currentKey=key;baseline=candidate=false;highHome=-1;celebrationUntilEngine=0;lastSample=0;
            InterlockedExchange(&mascotAnimationMode,2);
        }
        if(lastSample && now-lastSample>2000) { baseline=candidate=false;celebrationUntilEngine=0;InterlockedExchange(&mascotAnimationMode,2); }
        lastSample=now;
        const uint64_t engineNow=mascot_animation_clock_now();
        if(celebrationUntilEngine && engineNow>=celebrationUntilEngine) {
            celebrationUntilEngine=0;InterlockedExchange(&mascotAnimationMode,2);
            log_event("home_goal_celebration_finished score=%d:%d",h,a);
        }
        if(!baseline) {
            if(!candidate || h!=candidateHome || a!=candidateAway) { candidate=true;candidateHome=h;candidateAway=a;candidateSince=now; }
            if(now-candidateSince>=750) {
                scoreHome=h;scoreAway=a;highHome=h;baseline=true;candidate=false;
                log_event("goal_score_baseline home=%d away=%d",h,a);
            }
        } else if(h==scoreHome && a==scoreAway) candidate=false;
        else {
            if(!candidate || h!=candidateHome || a!=candidateAway) { candidate=true;candidateHome=h;candidateAway=a;candidateSince=now; }
            const bool homeGoal=(h==scoreHome+1 && a==scoreAway && h>highHome);
            if((h<scoreHome || a!=scoreAway) && celebrationUntilEngine) {
                celebrationUntilEngine=0;InterlockedExchange(&mascotAnimationMode,2);
            }
            if(now-candidateSince>=750) {
                const int oldHome=scoreHome,oldAway=scoreAway;
                scoreHome=h;scoreAway=a;candidate=false;if(h>highHome)highHome=h;
                if(homeGoal) {
                    InterlockedExchange(&mascotGoalEventSerial,h-1);
                    celebrationUntilEngine=mascot_animation_clock_now()+15000;InterlockedExchange(&mascotAnimationMode,3);
                    log_event("HOME_GOAL_CONFIRMED score=%d:%d previous=%d:%d; native_behavior=14 duration_engine_ms=15000",h,a,oldHome,oldAway);
                } else {
                    InterlockedExchange(&mascotAnimationMode,2);
                    log_event("score_change_without_home_goal score=%d:%d previous=%d:%d",h,a,oldHome,oldAway);
                }
            }
        }
        Sleep(100);
    }
}
