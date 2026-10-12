#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <vector>
#include <cstdlib>
#include "mascot_placement_policy.h"
#include "mascot_walk_clips.h"
#include "mascot_animation_variants.h"
#include "mascot_pose_policy.h"
struct MascotFrameContext { uintptr_t renderer,records;size_t count,selected;int home;unsigned int generation; };
static LONG mascotPlacementSession=1;
static unsigned int mascotPlacementGeneration=1;
static wchar_t gameDirectory[MAX_PATH];
static float targetPosition[3]={5850,0,3150},originalPosition[3]{},originalYaw=0;
static float mascotBindPose[31][16];
static uintptr_t mascotAnimatedRenderer,mascotAnimatedRecords;
static size_t mascotAnimatedIndex;
static unsigned int mascotPrivateSlot=73;
static bool mascotAnimationBound;
template<class T>static bool get(uintptr_t p,T& v){if(!p)return false;memcpy(&v,(void*)p,sizeof(v));return true;}
static void log_event(const char*,...){}
#include "mascot_walk_runtime.h"
#include "mascot_replay_history.h"

static int check_pose_library(const float* frames,const float* times,unsigned int count,float duration) {
    for(unsigned int i=0;i+1<count;++i)for(unsigned int n=0;n<8;++n) {
        const float t=times[i]+(times[i+1]-times[i])*(float)n/8;
        float sampled[31*7],pose[31][16];
        mascot_sample_baked_clip(frames,times,count,duration,t,sampled);
        mascot_retarget_baked_pose(sampled,pose);
        if(!mascot_pose_upright(pose))return 1;
        mascot_ground_pose(pose);
        float feet[2][3];mascot_pose_feet(pose,feet);
        if(fabsf(fminf(feet[0][1],feet[1][1])-mascotFootMarkers.floor)>.01f)return 2;
        mascot_blend_local_pose(pose,0,1.0f/30);mascot_orient_pose(pose,.5f);
        if(!mascot_pose_upright(pose))return 3;
    }
    return 0;
}
int wmain(int argc,wchar_t** argv) {
    if(argc<2)return 1;
    std::vector<int> clubs;
    for(int i=2;i<argc;++i) {
        wchar_t* end=nullptr;const long id=wcstol(argv[i],&end,10);
        if(!end || *end || id<1 || id>200000)return 19;
        clubs.push_back((int)id);
    }
    if(clubs.empty())clubs={1035,1043,383,568,569};
    wcsncpy_s(gameDirectory,argv[1],_TRUNCATE);
    for(int club:clubs) {
        wchar_t path[MAX_PATH];_snwprintf_s(path,MAX_PATH,_TRUNCATE,L"%ls\\data\\sceneassets\\mascot\\%d\\bind.bin",gameDirectory,club);
        FILE* f=nullptr;if(_wfopen_s(&f,path,L"rb")||!f)return 2;
        const size_t got=fread(mascotBindPose,1,sizeof(mascotBindPose),f);fclose(f);if(got!=sizeof(mascotBindPose))return 3;
        mascot_load_foot_markers(club);if(!mascotFootMarkersReady)return 4;
        if(check_pose_library(&mascotIdleFrames[0][0],mascotIdleTimes,mascotIdleFrameCount,mascotIdleDuration) ||
           check_pose_library(&mascotCheerFrames[0][0],mascotCheerTimes,mascotCheerFrameCount,mascotCheerDuration) ||
           check_pose_library(&mascotGoalFrames[0][0],mascotGoalTimes,mascotGoalFrameCount,mascotGoalDuration) ||
           check_pose_library(&mascotWalkFrames[0][0],mascotWalkTimes,mascotWalkFrameCount,mascotWalkDuration))return 5;
        for(const auto& clip:mascotGoalClips) {
            if(check_pose_library(clip.frames,clip.times,clip.count,clip.duration))return 27;
            for(unsigned int i=0;i<clip.count;++i) {
                const float lift=mascot_clip_lift(clip,clip.times[i]);
                if(!isfinite(lift)||lift<0||lift>50)return 28;
                float pose[31][16];mascot_retarget_baked_pose(clip.frames+i*217,pose);
                mascot_ground_pose(pose);
                for(unsigned int bone=0;bone<31;++bone)pose[bone][13]+=lift;
                float feet[2][3];mascot_pose_feet(pose,feet);
                if(fabsf(fminf(feet[0][1],feet[1][1])-mascotFootMarkers.floor-lift)>.02f)return 29;
            }
        }
        for(const auto& clip:mascotSupportClips)
            if(check_pose_library(clip.frames,clip.times,clip.count,clip.duration))return 30;
        // Check the raised, separated arms on each final mascot rig. Large
        // mascot heads need not have the proportions of the human source.
        unsigned int raised=0;
        for(unsigned int i=0;i<mascotGoalFrameCount;++i) {
            float pose[31][16];mascot_retarget_baked_pose(mascotGoalFrames[i],pose);
            const float height=pose[14][13]-pose[5][13];
            const float restHands=fmaxf(mascotBindPose[19][13],mascotBindPose[24][13]);
            const float dx=pose[19][12]-pose[24][12],dy=pose[19][13]-pose[24][13],dz=pose[19][14]-pose[24][14];
            if(fminf(pose[19][13],pose[24][13])>restHands+height*.12f &&
               sqrtf(dx*dx+dy*dy+dz*dz)>height*.15f)++raised;
        }
        if(raised<mascotGoalFrameCount/2)return 20;
        printf("PASS club=%d goal_arms_raised_separated=%u/%u separate_from_applause=1\n",club,raised,mascotGoalFrameCount);
        for(int direction:{-1,1}) {
            alignas(16) unsigned char record[80]{};
            MascotFrameContext frame{1,(uintptr_t)record,1,0,club,1};
            targetPosition[2]=direction<0?3150.0f:-3150.0f;
            mascotWalkRuntime={};mascot_walk_reset(frame,1000);
            if(mascotWalkRuntime.idleRemaining!=30)return 13;
            MascotWalkRuntime& s=mascotWalkRuntime;
            s.direction=direction<0?1:-1;s.idleRemaining=0;s.yaw=1.2f;
            float moved=0,expectedDistance=0;bool wasWalking=false,finished=false;uint64_t now=1000;
            for(unsigned int tick=0;tick<18000;++tick) {
                const float oldZ=s.position[2],oldPhase=s.walkTime;
                mascot_walk_update(frame,2,now,.016f);now+=16;
                if(tick==0)expectedDistance=fabsf(mascotGoalLineDestinations[s.nextWaypoint]-oldZ);
                float inputYaw=0,outputYaw=0;get((uintptr_t)record+0x1c,inputYaw);get((uintptr_t)record+0x2c,outputYaw);
                if(inputYaw!=0 || outputYaw!=0)return 6;
                if(s.turning && fabsf(s.position[2]-oldZ)>.001f)return 7;
                if(s.walkTime>oldPhase) {
                    const float expected=mascot_walk_advance(oldPhase,s.walkTime-oldPhase);
                    if(fabsf(fabsf(s.position[2]-oldZ)-expected)>.025f)return 8;
                    if((s.position[2]-oldZ)*s.direction<-.001f)return 9;
                    moved+=fabsf(s.position[2]-oldZ);
                }
                if(tick==300) {
                    const float z=s.position[2],yaw=s.yaw,phase=s.walkTime,idle=s.idleRemaining;
                    for(unsigned int pause=0;pause<500;++pause){mascot_walk_update(frame,2,now,0);now+=16;}
                    if(z!=s.position[2]||yaw!=s.yaw||phase!=s.walkTime||idle!=s.idleRemaining)return 10;
                }
                if(s.walking)wasWalking=true;
                if(wasWalking&&!s.walking){finished=true;break;}
            }
            if(!finished||fabsf(moved-expectedDistance)>.06f)return 11;
            if(s.idleRemaining!=30)return 14;
            printf("PASS club=%d direction=%d route_cm=%.3f pause=unchanged yaw=palette poses=upright\n",club,direction,moved);
            mascotAnimatedRenderer=frame.renderer;mascotAnimatedRecords=frame.records;mascotAnimatedIndex=0;mascotAnimationBound=true;
            const uint16_t slot=73;memcpy(record+0x40,&slot,sizeof(slot));
            mascot_walk_restore_live(frame.renderer,frame.records,frame.count);
            float restoredYaw=0;get((uintptr_t)record+0x1c,restoredYaw);if(restoredYaw!=originalYaw)return 12;
        }
    }
    {
        {
        static MascotReplayHistory history;
        history.bind(1043,1);
        float a[31][16],b[31][16],c[31][16];
        memcpy(a,mascotBindPose,sizeof(a));memcpy(b,a,sizeof(b));memcpy(c,a,sizeof(c));
        for(unsigned int bone=0;bone<31;++bone){b[bone][13]+=20;c[bone][13]+=10;}
        const float pa[3]={5850,0,3150},pb[3]={5850,0,3000},pc[3]={5850,0,2925};
        history.record(100,1000,pa,a,1,-1);history.record(110,2000,pb,b,3,112);history.record(120,3000,pc,c,3,118);
        float position[3],pose[31][16];int kind=0,clip=-1;bool clamped=false;
        for(double time:{120.,110.,100.,105.,110.,120.}) {
            if(!history.sample(time,position,pose,kind,clip,clamped)||clamped)return 34;
            const float expected=time<=110?(float)(time-100)*2:20-(float)(time-110);
            if(fabsf(pose[2][13]-a[2][13]-expected)>.001f)return 35;
            if(time==110 && (kind!=3 || clip!=112 || position[2]!=3000))return 36;
        }
        float paused[31][16];memcpy(paused,pose,sizeof(paused));
        for(unsigned int i=0;i<100;++i) {
            history.sample(120,position,pose,kind,clip,clamped);
            if(memcmp(paused,pose,sizeof(paused)) || history.count!=3)return 37;
        }
        history.sample(99,position,pose,kind,clip,clamped);if(!clamped||position[2]!=3150)return 38;
        history.bind(1035,2);if(history.sample(110,position,pose,kind,clip,clamped))return 39;
        for(unsigned int i=0;i<MascotReplayHistory::capacity+3;++i)history.record(100+i,1000+(uint64_t)i*40,pa,a,1,-1);
        if(history.count!=MascotReplayHistory::capacity || history.at(0).time!=103)return 40;
        puts("PASS replay history: backward/forward seek, jump height, position/clip restoration, stable pause, session isolation and ring retention");
        }
        for(unsigned int event=0;event<mascotGoalClipCount*2;++event) {
            unsigned int seen=0;
            for(unsigned int tick=0;tick<1500;++tick) {
                float phase=0,again=0;
                const unsigned int variant=mascot_goal_sequence(event,(float)tick*.01f,phase);
                if(mascot_goal_sequence(event,(float)tick*.01f,again)!=variant || phase!=again)return 31;
                if(variant>=mascotGoalClipCount || phase<0 || phase>=mascotGoalClips[variant].duration)return 32;
                seen|=1u<<variant;
            }
            if(!(seen&(seen-1)))return 33;
        }
        printf("PASS six native goal variants: several clips per goal, repeatable event/time selection; three support variants\n");
        alignas(16) unsigned char record[80]{};
        MascotFrameContext frame{1,(uintptr_t)record,1,0,1043,1};
        mascot_walk_reset(frame,1000);
        unsigned int interactionFrames=0;
        for(unsigned int tick=0;tick<1800;++tick) {
            mascot_walk_update(frame,2,1000+tick*16,1.0f/60);
            if(mascot_waypoint_interaction())++interactionFrames;
            if(tick<1798 && (mascotWalkRuntime.walking||mascotWalkRuntime.turning))return 16;
        }
        if(interactionFrames<899 || interactionFrames>901)return 17;
        mascot_walk_update(frame,2,30000,.05f);
        if(!mascotWalkRuntime.walking && !mascotWalkRuntime.turning)return 18;
        printf("PASS 30 second stop: 15 seconds interaction, no early departure\n");
        for(unsigned int start=0;start<mascotGoalLineDestinationCount;++start) {
            targetPosition[2]=mascotGoalLineDestinations[start];mascot_walk_reset(frame,1000);
            unsigned int seen=1u<<start;
            for(unsigned int choice=0;choice<60;++choice) {
                MascotWalkRuntime& s=mascotWalkRuntime;
                s.walking=s.turning=false;s.idleRemaining=0;
                const float previous=s.position[2];
                mascot_walk_update(frame,2,1000+choice*32,.016f);
                const float next=mascotGoalLineDestinations[s.nextWaypoint];
                if(s.nextWaypoint==s.waypoint || fabsf(next-previous)>600.01f || next*previous<=0)return 15;
                // Returning is allowed only when no less-recent eligible stop exists.
                for(unsigned int i=0;i<mascotGoalLineDestinationCount;++i)
                    if(i!=s.waypoint && fabsf(mascotGoalLineDestinations[i]-previous)<=600.01f &&
                       s.waypointLastVisit[i]<s.waypointLastVisit[s.nextWaypoint])return 20;
                seen|=1u<<s.nextWaypoint;
                s.position[2]=next;s.turning=false;s.walking=true;
                mascot_walk_update(frame,2,1016+choice*32,.016f);
                if(s.walking || s.waypointLastVisit[s.waypoint]!=s.waypointVisitSerial)return 21;
            }
            if(seen!=(start<5?0x1fu:0x3e0u))return 22;
        }
        printf("PASS 600 local choices: max 6 metres, both five-stop regions explored, least-recent neighbour preferred\n");
        // Repeat goal interruptions, including a paused goal/replay. Arrival
        // history must not count destinations abandoned by the celebration.
        for(unsigned int goal=0;goal<3;++goal) {
            targetPosition[2]=3150;mascot_walk_reset(frame,1000);
            MascotWalkRuntime& s=mascotWalkRuntime;s.idleRemaining=0;
            mascot_walk_update(frame,2,1016,.016f);
            s.position[2]=2925;s.walking=true;s.turning=false;
            const float z=s.position[2];const unsigned int visits=s.waypointVisitSerial;
            for(unsigned int tick=0;tick<900;++tick)mascot_walk_update(frame,3,1032+tick*16,1.0f/60);
            if(!s.cheering || s.walking || s.turning || s.position[2]!=z || s.waypointVisitSerial!=visits)return 23;
            const float clip=s.clipTime;
            for(unsigned int tick=0;tick<300;++tick)mascot_walk_update(frame,3,16032+tick*16,0);
            if(s.clipTime!=clip || s.position[2]!=z)return 24;
            mascot_walk_update(frame,2,22000,.016f);
            if(s.cheering || s.walking || s.turning || s.idleRemaining<29.98f)return 25;
            s.idleRemaining=0;mascot_walk_update(frame,2,22016,.016f);
            if(fabsf(mascotGoalLineDestinations[s.nextWaypoint]-z)>600.01f)return 26;
        }
        printf("PASS three home-goal interruptions: stationary cheer, pause freezes phase, 30-second rest then nearby route\n");
    }
    alignas(16) unsigned char benchmarkRecord[80]{};
    MascotFrameContext benchmark{1,(uintptr_t)benchmarkRecord,1,0,569,1};
    mascotWalkRuntime={};targetPosition[2]=3150;mascot_walk_reset(benchmark,1000);mascotWalkRuntime.idleRemaining=0;
    LARGE_INTEGER frequency{},begin{},end{};
    QueryPerformanceFrequency(&frequency);QueryPerformanceCounter(&begin);
    for(unsigned int i=0;i<10000;++i)mascot_walk_update(benchmark,2,1000+i*16,.016f);
    QueryPerformanceCounter(&end);
    const double micros=(double)(end.QuadPart-begin.QuadPart)*1.0e6/(double)frequency.QuadPart/10000;
    printf("Offline locomotion cost: %.2f us/callback (no engine/driver/log cost)\n",micros);
    return 0;
}
