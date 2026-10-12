#pragma once
#include <limits.h>
#include "mascot_locomotion_math.h"

struct MascotWalkQuaternion { float x, y, z, w; };
struct MascotWalkRuntime {
    bool ready=false, walking=false, turning=false, cheering=false, hasPose=false, transitioning=false;
    int home=-1, direction=0, poseKind=-1;
    unsigned int waypoint=0, nextWaypoint=0;
    unsigned int generation=0, waypointVisitSerial=0;
    unsigned int waypointLastVisit[mascotGoalLineDestinationCount]{};
    LONG session=0;
    uint64_t lastTick=0, transitionTick=0, seatPollTick=0;
    float position[3]{}, idleRemaining=0, walkTime=0, walkDistance=0;
    float yaw=0;
    float clipTime=0, transitionPose[31*7]{}, currentPose[31*7]{};
    float blendElapsed=0, groundLift=0;
    bool hasGroundLift=false;
    float visualLift=0, liftBlendSource=0;
    float lastLocal[31][16]{}, blendSource[31][16]{};
};
static MascotWalkRuntime mascotWalkRuntime;
static constexpr float mascotWalkPlaybackRate=1.0f;
static constexpr float mascotWaypointDwellSeconds=30.0f;
static constexpr float mascotWaypointInteractionSeconds=15.0f;
static constexpr float mascotWaypointMaxTravelCm=600.0f;
static bool mascot_waypoint_interaction() {
    const MascotWalkRuntime& s=mascotWalkRuntime;
    const float idle=(mascotWaypointDwellSeconds-mascotWaypointInteractionSeconds)*.5f;
    return !s.walking && !s.turning && s.idleRemaining<=idle+mascotWaypointInteractionSeconds && s.idleRemaining>idle;
}

struct MascotFootMarkers {
    unsigned int magic,version,bones,floats;
    float floor;
    float values[2][31][4];
};
static MascotFootMarkers mascotFootMarkers{};
static bool mascotFootMarkersReady;

static MascotWalkQuaternion mascot_wq_norm(MascotWalkQuaternion q) {
    const float n=sqrtf(q.x*q.x+q.y*q.y+q.z*q.z+q.w*q.w);
    if(n<1e-8f || !isfinite(n)) return {0,0,0,1};
    return {q.x/n,q.y/n,q.z/n,q.w/n};
}
static MascotWalkQuaternion mascot_wq_mul(MascotWalkQuaternion a,MascotWalkQuaternion b) {
    return mascot_wq_norm({a.w*b.x+a.x*b.w+a.y*b.z-a.z*b.y,
        a.w*b.y-a.x*b.z+a.y*b.w+a.z*b.x,a.w*b.z+a.x*b.y-a.y*b.x+a.z*b.w,
        a.w*b.w-a.x*b.x-a.y*b.y-a.z*b.z});
}
static MascotWalkQuaternion mascot_wq_inverse(MascotWalkQuaternion q) { return {-q.x,-q.y,-q.z,q.w}; }
static MascotWalkQuaternion mascot_wq_from_matrix(const float* m) {
    const float m00=m[0],m11=m[5],m22=m[10]; MascotWalkQuaternion q{};
    const float trace=m00+m11+m22;
    if(trace>0){const float s=sqrtf(trace+1.0f)*2;q.w=.25f*s;q.x=(m[6]-m[9])/s;q.y=(m[8]-m[2])/s;q.z=(m[1]-m[4])/s;}
    else if(m00>m11 && m00>m22){const float s=sqrtf(1+m00-m11-m22)*2;q.w=(m[6]-m[9])/s;q.x=.25f*s;q.y=(m[4]+m[1])/s;q.z=(m[8]+m[2])/s;}
    else if(m11>m22){const float s=sqrtf(1+m11-m00-m22)*2;q.w=(m[8]-m[2])/s;q.x=(m[4]+m[1])/s;q.y=.25f*s;q.z=(m[9]+m[6])/s;}
    else{const float s=sqrtf(1+m22-m00-m11)*2;q.w=(m[1]-m[4])/s;q.x=(m[8]+m[2])/s;q.y=(m[9]+m[6])/s;q.z=.25f*s;}
    return mascot_wq_norm(q);
}
static void mascot_wq_rotate(MascotWalkQuaternion q,const float v[3],float out[3]) {
    const float tx=2*(q.y*v[2]-q.z*v[1]),ty=2*(q.z*v[0]-q.x*v[2]),tz=2*(q.x*v[1]-q.y*v[0]);
    out[0]=v[0]+q.w*tx+(q.y*tz-q.z*ty);out[1]=v[1]+q.w*ty+(q.z*tx-q.x*tz);out[2]=v[2]+q.w*tz+(q.x*ty-q.y*tx);
}
static void mascot_wq_to_matrix(MascotWalkQuaternion in,const float p[3],float m[16]) {
    const MascotWalkQuaternion q=mascot_wq_norm(in);const float xx=q.x*q.x,yy=q.y*q.y,zz=q.z*q.z,xy=q.x*q.y,xz=q.x*q.z,yz=q.y*q.z,wx=q.w*q.x,wy=q.w*q.y,wz=q.w*q.z;
    m[0]=1-2*(yy+zz);m[1]=2*(xy+wz);m[2]=2*(xz-wy);m[3]=0;
    m[4]=2*(xy-wz);m[5]=1-2*(xx+zz);m[6]=2*(yz+wx);m[7]=0;
    m[8]=2*(xz+wy);m[9]=2*(yz-wx);m[10]=1-2*(xx+yy);m[11]=0;
    m[12]=p[0];m[13]=p[1];m[14]=p[2];m[15]=1;
}
static MascotWalkQuaternion mascot_wq_nlerp(MascotWalkQuaternion a,MascotWalkQuaternion b,float t) {
    const float dot=a.x*b.x+a.y*b.y+a.z*b.z+a.w*b.w;if(dot<0)b={-b.x,-b.y,-b.z,-b.w};
    return mascot_wq_norm({a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t,a.z+(b.z-a.z)*t,a.w+(b.w-a.w)*t});
}
static void mascot_sample_baked_clip(const float* frames,const float* times,unsigned int count,float duration,float time,float out[31*7]) {
    if(!count||duration<=0){memset(out,0,31*7*sizeof(float));return;}
    time=fmodf(time,duration);if(time<0)time+=duration;unsigned int lo=0;
    while(lo+1<count&&times[lo+1]<time)++lo;const unsigned int hi=(lo+1<count)?lo+1:lo;
    const float span=times[hi]-times[lo],alpha=span>1e-6f?fmaxf(0,fminf(1,(time-times[lo])/span)):0;
    const float* a=frames+lo*(31*7);const float* b=frames+hi*(31*7);
    for(unsigned int j=0;j<31;++j){const unsigned int k=j*7;for(unsigned int n=0;n<3;++n)out[k+n]=a[k+n]+(b[k+n]-a[k+n])*alpha;
        const MascotWalkQuaternion q=mascot_wq_nlerp({a[k+3],a[k+4],a[k+5],a[k+6]},{b[k+3],b[k+4],b[k+5],b[k+6]},alpha);
        out[k+3]=q.x;out[k+4]=q.y;out[k+5]=q.z;out[k+6]=q.w;
    }
}
static void mascot_retarget_baked_pose(const float src[31*7],float out[31][16]) {
    static const int parent[31]={-1,0,1,2,3,4,5,2,7,8,9,2,11,12,13,14,13,16,17,18,19,13,21,22,23,24,9,5,0,28,0};
    MascotWalkQuaternion delta[31],actual[31];float pos[31][3];
    for(unsigned int j=0;j<31;++j){const unsigned int k=j*7;const MascotWalkQuaternion canonicalBind={mascotWalkBindPose[k+3],mascotWalkBindPose[k+4],mascotWalkBindPose[k+5],mascotWalkBindPose[k+6]};
        const MascotWalkQuaternion animated={src[k+3],src[k+4],src[k+5],src[k+6]};delta[j]=mascot_wq_mul(animated,mascot_wq_inverse(canonicalBind));actual[j]=mascot_wq_from_matrix(mascotBindPose[j]);}
    for(unsigned int j=0;j<31;++j){const int p=parent[j];if(p<0||j==2){pos[j][0]=mascotBindPose[j][12];pos[j][1]=mascotBindPose[j][13];pos[j][2]=mascotBindPose[j][14];}
        else{const float v[3]={mascotBindPose[j][12]-mascotBindPose[p][12],mascotBindPose[j][13]-mascotBindPose[p][13],mascotBindPose[j][14]-mascotBindPose[p][14]};float r[3];mascot_wq_rotate(delta[p],v,r);pos[j][0]=pos[p][0]+r[0];pos[j][1]=pos[p][1]+r[1];pos[j][2]=pos[p][2]+r[2];}
        mascot_wq_to_matrix(mascot_wq_mul(delta[j],actual[j]),pos[j],out[j]);}
}
static void mascot_load_foot_markers(int club) {
    mascotFootMarkersReady=false;mascotFootMarkers={};
    wchar_t path[MAX_PATH];
    _snwprintf_s(path,MAX_PATH,_TRUNCATE,L"%ls\\data\\sceneassets\\mascot\\%u\\locomotion_feet.bin",gameDirectory,(unsigned int)club);
    FILE* file=nullptr;if(_wfopen_s(&file,path,L"rb") || !file)return;
    MascotFootMarkers markers{};
    const bool complete=fread(&markers,1,sizeof(markers),file)==sizeof(markers) && fgetc(file)==EOF;
    fclose(file);
    if(!complete || markers.magic!=0x3146534d || markers.version!=1 || markers.bones!=31 || markers.floats!=248 ||
       !isfinite(markers.floor) || fabsf(markers.floor)>100)return;
    for(unsigned int side=0;side<2;++side) {
        float total=0;
        for(unsigned int bone=0;bone<31;++bone) {
            for(float value:markers.values[side][bone])if(!isfinite(value)||fabsf(value)>1000)return;
            const float weight=markers.values[side][bone][3];
            if(weight<0 || weight>1.001f)return;
            total+=weight;
        }
        if(fabsf(total-1)>0.01f)return;
    }
    mascotFootMarkers=markers;mascotFootMarkersReady=true;
}
static void mascot_pose_feet(const float pose[31][16],float feet[2][3]) {
    if(!mascotFootMarkersReady) {
        for(unsigned int side=0;side<2;++side)for(unsigned int axis=0;axis<3;++axis)
            feet[side][axis]=pose[side?9:5][12+axis];
        return;
    }
    memset(feet,0,2*3*sizeof(float));
    for(unsigned int side=0;side<2;++side)for(unsigned int bone=0;bone<31;++bone)
        for(unsigned int axis=0;axis<3;++axis)for(unsigned int col=0;col<4;++col)
            feet[side][axis]+=pose[bone][col*4+axis]*mascotFootMarkers.values[side][bone][col];
}
static void mascot_walk_feet_at(float time,float feet[2][3]) {
    float sampled[31*7],pose[31][16];
    mascot_sample_baked_clip(&mascotWalkFrames[0][0],mascotWalkTimes,mascotWalkFrameCount,mascotWalkDuration,time,sampled);
    mascot_retarget_baked_pose(sampled,pose);mascot_pose_feet(pose,feet);
}
static float mascot_walk_advance(float phase,float delta) {
    // Split at source sample cadence so a support-foot change is measured
    // on each interval instead of applying a single average-speed root.
    float total=0,feet[2][3];mascot_walk_feet_at(phase,feet);
    while(delta>0.000001f) {
        const float step=fminf(delta,1.0f/30.0f);
        float next[2][3];mascot_walk_feet_at(phase+step,next);
        total+=mascot_contact_advance(feet,next);
        memcpy(feet,next,sizeof(feet));phase+=step;delta-=step;
    }
    return total;
}
static void mascot_ground_pose(float pose[31][16],float dt=-1) {
    float feet[2][3];mascot_pose_feet(pose,feet);
    const float floor=mascotFootMarkersReady?mascotFootMarkers.floor:fminf(mascotBindPose[5][13],mascotBindPose[9][13]);
    const float lift=floor-fminf(feet[0][1],feet[1][1]);
    if(!isfinite(lift)||fabsf(lift)>30)return;
    MascotWalkRuntime& s=mascotWalkRuntime;
    if(!s.hasGroundLift || dt<0){s.groundLift=lift;s.hasGroundLift=true;}
    else s.groundLift+=(lift-s.groundLift)*(1-expf(-fmaxf(0,dt)/.08f));
    for(unsigned int bone=0;bone<31;++bone)pose[bone][13]+=s.groundLift;
}
static void mascot_blend_local_pose(float pose[31][16],int kind,float dt) {
    MascotWalkRuntime& s=mascotWalkRuntime;
    if(s.hasPose && s.poseKind!=kind) {
        s.liftBlendSource=s.visualLift;
        memcpy(s.blendSource,s.lastLocal,sizeof(s.blendSource));
        s.blendElapsed=0;s.transitioning=true;
    }
    s.poseKind=kind;
    if(s.transitioning) {
        const float duration=(kind==0)?.45f:.35f;
        s.blendElapsed+=fmaxf(0,dt);
        const float linear=fminf(1,s.blendElapsed/duration);
        const float t=linear*linear*(3-2*linear);
        for(unsigned int bone=0;bone<31;++bone) {
            float p[3];for(unsigned int axis=0;axis<3;++axis)
                p[axis]=s.blendSource[bone][12+axis]+(pose[bone][12+axis]-s.blendSource[bone][12+axis])*t;
            mascot_wq_to_matrix(mascot_wq_nlerp(mascot_wq_from_matrix(s.blendSource[bone]),mascot_wq_from_matrix(pose[bone]),t),p,pose[bone]);
        }
        if(linear>=1)s.transitioning=false;
    }
    memcpy(s.lastLocal,pose,sizeof(s.lastLocal));
}
static void mascot_orient_pose(float pose[31][16],float yaw) {
    // Apply actor heading once, in the private palette. Native actor yaw is
    // zero, so draw preparation cannot overwrite or double this rotation.
    const float cosine=cosf(yaw),sine=sinf(yaw);
    for(unsigned int bone=0;bone<31;++bone)for(unsigned int column=0;column<4;++column) {
        const unsigned int k=column*4;const float x=pose[bone][k],z=pose[bone][k+2];
        pose[bone][k]=cosine*x+sine*z;pose[bone][k+2]=-sine*x+cosine*z;
    }
}
static unsigned int mascot_nearest_waypoint(float z) {
    unsigned int best=0;float nearest=1.0e30f;for(unsigned int i=0;i<mascotGoalLineDestinationCount;++i){const float d=fabsf(z-mascotGoalLineDestinations[i]);if(d<nearest){nearest=d;best=i;}}return best;
}
static unsigned int mascot_local_destination(const MascotWalkRuntime& s,unsigned int at) {
    unsigned int best=at,oldest=UINT_MAX;
    float nearest=1.0e30f;
    for(unsigned int i=0;i<mascotGoalLineDestinationCount;++i) {
        const float travel=fabsf(mascotGoalLineDestinations[i]-s.position[2]);
        if(i==at || travel>mascotWaypointMaxTravelCm+.01f)continue;
        // Only nearby stops are eligible. Prefer the least recently visited
        // neighbour; the distance breaks ties without a cross-goal detour.
        if(s.waypointLastVisit[i]<oldest || (s.waypointLastVisit[i]==oldest && travel<nearest)) {
            best=i;oldest=s.waypointLastVisit[i];nearest=travel;
        }
    }
    return best;
}
static void mascot_walk_reset(const MascotFrameContext& frame,uint64_t now) {
    MascotWalkRuntime& s=mascotWalkRuntime;s={};s.ready=true;s.home=frame.home;s.generation=frame.generation;s.session=InterlockedCompareExchange(&mascotPlacementSession,0,0);s.lastTick=now;s.yaw=originalYaw;
    memcpy(s.position,targetPosition,sizeof(s.position));s.waypoint=mascot_nearest_waypoint(s.position[2]);uint32_t seed=(uint32_t)now^(uint32_t)(now>>32)^(uint32_t)frame.home^(uint32_t)s.session;
    s.waypointVisitSerial=1;s.waypointLastVisit[s.waypoint]=1;
    s.idleRemaining=mascotWaypointDwellSeconds;s.direction=(seed&1)?1:-1;if(s.waypoint==0)s.direction=1;if(s.waypoint+1>=mascotGoalLineDestinationCount)s.direction=-1;
    s.nextWaypoint=(unsigned int)((int)s.waypoint+s.direction);
}
static void mascot_walk_restore_live(uintptr_t renderer,uintptr_t records,size_t count) {
    MascotWalkRuntime& s=mascotWalkRuntime;if(!s.ready)return;
    // Restore only within the vector validated for this callback. A readable
    // allocation alone cannot prove that a previous scene still owns it.
    uint16_t binding=0;
    if(renderer==mascotAnimatedRenderer && records==mascotAnimatedRecords &&
       mascotAnimationBound && mascotAnimatedIndex<count &&
       get(records+mascotAnimatedIndex*0x50+0x40,binding) && binding==mascotPrivateSlot) {
        memcpy((void*)(records+mascotAnimatedIndex*0x50+0x20),originalPosition,sizeof(originalPosition));
        memcpy((void*)(records+mascotAnimatedIndex*0x50+0x2c),&originalYaw,sizeof(originalYaw));
        memcpy((void*)(records+mascotAnimatedIndex*0x50+0x1c),&originalYaw,sizeof(originalYaw));
    }
    s.ready=false;s.walking=false;s.hasPose=false;
}
static void mascot_walk_update(const MascotFrameContext& frame,LONG mode,uint64_t now,float engineDt) {
    MascotWalkRuntime& s=mascotWalkRuntime;
    const LONG session=InterlockedCompareExchange(&mascotPlacementSession,0,0);
    if(!s.ready||s.home!=frame.home||s.generation!=frame.generation||s.session!=session)
        mascot_walk_reset(frame,now);
    s.lastTick=now;
    const float dt=isfinite(engineDt)?fmaxf(0,fminf(.05f,engineDt)):0;
    const bool cheer=mode==3;
    if(dt>0) {
        if(cheer) {
            if(!s.cheering){s.cheering=true;s.walking=false;s.turning=false;s.clipTime=0;}
            s.clipTime+=dt;
        } else {
            if(s.cheering){s.cheering=false;s.walking=false;s.turning=false;s.idleRemaining=mascotWaypointDwellSeconds;s.clipTime=0;}
            else s.clipTime+=dt;
            if(!s.walking && !s.turning) {
                s.idleRemaining-=dt;
                if(s.idleRemaining<=0) {
                    const unsigned int at=mascot_nearest_waypoint(s.position[2]);
                    s.waypoint=at;s.nextWaypoint=mascot_local_destination(s,at);
                    s.direction=mascotGoalLineDestinations[s.nextWaypoint]>s.position[2]?1:-1;
                    s.walkTime=s.walkDistance=0;s.turning=s.nextWaypoint!=at;
                    if(!s.turning)s.idleRemaining=mascotWaypointDwellSeconds;
                }
            }
        }
        const bool route=(s.walking||s.turning)&&!cheer;
        const float heading=route?atan2f(0,mascotGoalLineDestinations[s.nextWaypoint]-s.position[2]):atan2f(-targetPosition[0],-s.position[2]);
        s.yaw=mascot_turn_heading(s.yaw,heading,dt);
        if(s.turning && fabsf(mascot_wrap_heading(heading-s.yaw))<.04f) {
            s.turning=false;s.walking=true;
            log_event("walk_begin club=%d from_z=%.2f to_z=%.2f heading=%.3f feet=%s cadence=1",frame.home,s.position[2],mascotGoalLineDestinations[s.nextWaypoint],s.yaw,mascotFootMarkersReady?"skin_markers":"foot_joints");
        }
        if(s.walking && !cheer && fabsf(mascot_wrap_heading(heading-s.yaw))<.04f) {
            const float goal=mascotGoalLineDestinations[s.nextWaypoint];
            const float remaining=goal-s.position[2];
            float phaseAdvance=dt*mascotWalkPlaybackRate;
            float travel=mascot_walk_advance(s.walkTime,phaseAdvance);
            if(isfinite(travel) && travel<=dt*400) {
                if(travel>fabsf(remaining)) {
                    // Trim the final animation phase with the route distance;
                    // do not complete a full step while clipping only the root.
                    float lo=0,hi=phaseAdvance;
                    for(unsigned int i=0;i<12;++i) {
                        const float mid=(lo+hi)*.5f;
                        if(mascot_walk_advance(s.walkTime,mid)>fabsf(remaining))hi=mid;else lo=mid;
                    }
                    phaseAdvance=lo;travel=mascot_walk_advance(s.walkTime,phaseAdvance);
                }
                s.walkTime+=phaseAdvance;
                s.walkDistance+=travel;
                s.position[2]+=remaining<0?-travel:travel;
                if(fabsf(goal-s.position[2])<.02f) {
                    s.position[2]=goal;s.waypoint=s.nextWaypoint;s.walking=false;
                    s.waypointLastVisit[s.waypoint]=++s.waypointVisitSerial;
                    s.idleRemaining=mascotWaypointDwellSeconds;s.clipTime=0;
                    log_event("walk_end club=%d z=%.2f distance_cm=%.2f",frame.home,s.position[2],s.walkDistance);
                }
            }
        }
    }
    s.position[0]=targetPosition[0];s.position[1]=originalPosition[1];
    if(frame.records&&frame.selected<frame.count) {
        const uintptr_t rec=frame.records+frame.selected*0x50;
        memcpy((void*)(rec+0x20),s.position,sizeof(s.position));
        // Heading is already applied to the private palette. Keep both native
        // record angles neutral to avoid a second actor rotation.
        const float paletteHeading=0;
        memcpy((void*)(rec+0x1c),&paletteHeading,sizeof(paletteHeading));
        memcpy((void*)(rec+0x2c),&paletteHeading,sizeof(paletteHeading));
    }
}
