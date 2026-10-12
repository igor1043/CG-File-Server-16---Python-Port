#pragma once

// Only the scene callback owns this history. The score worker never reads or
// changes it. Store final palette poses, so jumps, blends and clip choices are
// reproduced rather than advanced again during a seek.
struct MascotReplayFrame {
    double time=0;
    float position[3]{},pose[31*7]{};
    int kind=0,clip=-1;
};
struct MascotReplayHistory {
    static constexpr unsigned int capacity=8192;
    MascotReplayFrame frames[capacity]{};
    unsigned int head=0,count=0;
    int home=-1;LONG session=0;
    uint64_t lastWall=0;
    bool ready=false;
    const MascotReplayFrame& at(unsigned int logical) const { return frames[(head+logical)%capacity]; }
    void reset(int nextHome,LONG nextSession) { head=count=0;home=nextHome;session=nextSession;lastWall=0;ready=true; }
    void bind(int nextHome,LONG nextSession) { if(!ready || home!=nextHome || session!=nextSession)reset(nextHome,nextSession); }
    void record(double time,uint64_t wall,const float position[3],const float pose[31][16],int kind,int clip) {
        if(!isfinite(time) || time<0)return;
        if(count && time<at(count-1).time-.001)reset(home,session);
        if(count && time<=at(count-1).time+.000001)return;
        // At most 30 stored poses per real second. A transition is retained
        // immediately even when it lands between two regular sample ticks.
        if(count && wall-lastWall<33 && at(count-1).kind==kind && at(count-1).clip==clip)return;
        unsigned int slot=(head+count)%capacity;
        if(count==capacity){slot=head;head=(head+1)%capacity;}else ++count;
        MascotReplayFrame& f=frames[slot];f.time=time;f.kind=kind;f.clip=clip;
        memcpy(f.position,position,sizeof(f.position));
        for(unsigned int bone=0;bone<31;++bone) {
            const unsigned int k=bone*7;const auto q=mascot_wq_from_matrix(pose[bone]);
            for(unsigned int axis=0;axis<3;++axis)f.pose[k+axis]=pose[bone][12+axis];
            f.pose[k+3]=q.x;f.pose[k+4]=q.y;f.pose[k+5]=q.z;f.pose[k+6]=q.w;
        }
        lastWall=wall;
    }
    bool sample(double time,float position[3],float pose[31][16],int& kind,int& clip,bool& clamped) const {
        if(!count || !isfinite(time))return false;
        clamped=time<at(0).time || time>at(count-1).time;
        unsigned int lo=0,hi=count-1;
        if(time<=at(0).time)hi=0;
        else if(time>=at(count-1).time)lo=hi;
        else {
            while(hi-lo>1){const unsigned int mid=lo+(hi-lo)/2;if(at(mid).time<=time)lo=mid;else hi=mid;}
        }
        const auto& a=at(lo);const auto& b=at(hi);
        const double span=b.time-a.time;
        const float alpha=span>1e-9?(float)fmax(0,fmin(1,(time-a.time)/span)):0;
        kind=alpha<.5f?a.kind:b.kind;clip=alpha<.5f?a.clip:b.clip;
        for(unsigned int axis=0;axis<3;++axis)position[axis]=a.position[axis]+(b.position[axis]-a.position[axis])*alpha;
        for(unsigned int bone=0;bone<31;++bone) {
            const unsigned int k=bone*7;float p[3];
            for(unsigned int axis=0;axis<3;++axis)p[axis]=a.pose[k+axis]+(b.pose[k+axis]-a.pose[k+axis])*alpha;
            const auto q=mascot_wq_nlerp({a.pose[k+3],a.pose[k+4],a.pose[k+5],a.pose[k+6]},
                                       {b.pose[k+3],b.pose[k+4],b.pose[k+5],b.pose[k+6]},alpha);
            mascot_wq_to_matrix(q,p,pose[bone]);
        }
        return true;
    }
};
