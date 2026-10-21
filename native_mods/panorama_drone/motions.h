#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
namespace panorama {
struct Vec {float x=0,y=0,z=0;};
inline constexpr Vec operator+(Vec a,Vec b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
inline constexpr Vec operator-(Vec a,Vec b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
inline constexpr Vec operator*(Vec a,float k){return {a.x*k,a.y*k,a.z*k};}
inline float dot(Vec a,Vec b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline Vec cross(Vec a,Vec b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline bool unit(Vec& a){const float n=std::sqrt(dot(a,a));if(!std::isfinite(n)||n<.001f)return false;a=a*(1/n);return true;}
inline float smooth(float t){t=std::clamp(t,0.f,1.f);return std::clamp(t*t*t*(10+t*(-15+6*t)),0.f,1.f);}
inline Vec mix(Vec a,Vec b,float t){return a+(b-a)*t;}
struct Pose {Vec eye,target;float fov=55;};
enum class MotionKind {Curve,CircleOrbit,CircleTurn,ExteriorOrbit};
struct Motion {
 const char* id;Vec a,b,c,ta,tb,tc;float fov;
 Vec d{},td{};float endFov=0,durationScale=1;bool cubic=false,exterior=false;
 bool pitchEdge=false;MotionKind kind=MotionKind::Curve;
 float minimumHeight=8000;
};
inline constexpr Motion cinema(const char* id,Vec a,Vec b,Vec c,Vec d,Vec ta,Vec tb,Vec tc,Vec td,float from,float to,float durationScale=1,bool exterior=false,bool pitchEdge=false){
 return {id,a,b,c,ta,tb,tc,from,d,td,to,durationScale,true,exterior,pitchEdge};
}
// Centimetres in rendered world space. Exterior arrivals cross the stand rim
// high above the pitch, descending only after the camera is inside the bowl.
// No geometry or texture reloads are needed; exterior shells depend on the model.
inline constexpr Motion motions[]={
 {"low_pitch_flight",{-3900,190,-1100},{-1800,260,-850},{900,400,-500},{-1300,100,0},{1000,100,0},{3600,100,0},62},
 {"centre_takeoff",{-900,240,-300},{-700,1500,-250},{-400,3000,-200},{600,80,0},{350,60,0},{200,40,0},60},
 {"diagonal_crossing",{-3900,1100,-2200},{-900,1400,-500},{2400,1700,1600},{-700,90,0},{1500,90,600},{3900,90,1800},58},
 {"centre_orbit",{-1700,1500,-1900},{0,1500,-2500},{1700,1500,-1900},{0,60,0},{0,60,0},{0,60,0},58},
 {"goal_approach",{1500,800,-500},{2700,650,-350},{3900,500,-200},{5100,100,0},{5100,100,0},{5100,100,0},52},
 {"goal_reveal",{4400,250,1000},{4350,1300,1100},{4200,2300,1400},{3100,100,0},{1300,70,0},{0,50,0},60},
 {"touchline_travel",{-3000,750,-2400},{0,850,-2400},{3000,950,-2400},{-2000,90,0},{0,90,0},{2000,90,0},57},
 {"corner_arc",{3800,550,-2300},{4200,700,-1600},{4300,850,-700},{2900,100,-500},{3000,100,0},{3100,100,500},58},
 {"overhead_pitch",{-1300,3100,-180},{0,3100,-180},{1300,3100,-180},{-1300,30,0},{0,30,0},{1300,30,0},64},
 {"cinematic_descent",{-2600,2800,-1700},{-2500,1600,-1400},{-2300,650,-1100},{800,60,0},{1000,80,0},{1300,100,0},56},
 // An elevated pitch-side stand view, without entering the stand geometry.
 {"elevated_stand_view",{-1600,2100,-2600},{0,2100,-2600},{1600,2100,-2600},{-500,70,0},{0,70,0},{500,70,0},59},
 {"wide_pullback",{3300,600,600},{2000,1600,1000},{500,2700,1400},{4900,90,0},{3000,70,0},{800,50,0},62},
 cinema("exterior_touchline_arrival",{-1800,9200,-10800},{-1500,10500,-7400},{-900,9200,-1400},{-700,2100,-900}, {0,0,-2600},{0,0,-1000},{1000,80,0},{1800,100,0},56,55,1.6f,true),
 cinema("exterior_goal_arrival",{11800,9600,800},{7900,10500,600},{2400,9200,200},{1700,2200,100}, {4300,0,0},{2300,0,0},{0,60,0},{-3000,100,0},56,54,1.6f,true),
 cinema("exterior_corner_arrival",{-10800,10000,-7900},{-7400,11000,-5300},{-2100,9500,-900},{-1600,2500,-700}, {-3600,0,-2200},{-1600,0,-1000},{1000,60,500},{2600,100,800},58,56,1.6f,true),
 cinema("exterior_reverse_arrival",{1200,9500,10800},{1000,10800,7400},{400,9400,1300},{200,2400,800}, {0,0,2600},{0,0,1000},{-700,60,0},{-1800,90,0},56,55,1.6f,true),
 cinema("stadium_aerial_reveal",{-9800,8500,-6100},{-7200,9500,-6700},{-2500,10200,-5600},{1800,10500,-3900}, {-2800,50,-1800},{-1600,50,-1200},{0,50,0},{0,50,0},56,60,1.4f,true),
 cinema("bowl_departure",{800,2600,-500},{1200,9000,-1200},{1600,11000,-6900},{1800,10000,-10600}, {0,80,0},{0,50,0},{0,50,-1600},{0,50,-3000},54,56,1.6f,true),
 cinema("centre_sky_crane",{-600,900,-1000},{-1100,1900,-1500},{-1700,3700,-2200},{-1900,4800,-2400}, {800,90,0},{600,80,0},{200,50,0},{0,30,0},52,63,1.15f),
 cinema("goal_line_dolly",{4100,260,-1600},{4300,340,-600},{4300,460,700},{4100,650,1700}, {5150,130,-300},{5150,120,-100},{5150,120,100},{5150,130,300},53,57,1.1f),
 cinema("pitch_sweeping_arc",{-3500,1000,-1700},{-2500,1600,-2400},{900,1900,-2300},{2700,1500,-1400}, {-1500,100,300},{-600,100,600},{900,100,500},{2500,100,100},56,60,1.25f),
 cinema("centre_circle_portrait",{-650,1300,-850},{-300,1550,-1100},{650,1550,-900},{1050,1300,-200}, {0,50,0},{0,50,0},{0,50,0},{0,50,0},48,52,1.1f),
 cinema("crossbar_cinema",{4300,320,-800},{3900,420,-300},{3300,650,500},{2700,900,1000}, {5150,150,0},{4800,140,0},{4000,120,0},{3000,100,0},50,58,1.1f),
 cinema("grandstand_parallax",{-3300,1800,-2200},{-1200,2200,-2500},{1400,2300,-2500},{3300,1900,-2200}, {-800,650,3000},{-300,800,3200},{300,800,3200},{800,650,3000},58,60,1.25f),
 // Standard 105 x 68m pitch: goal planes X=+/-5250, penalty marks +/-4150.
 // Cameras stay in front of the goal plane; only their targets reach the net.
 cinema("goal_mouth_sweep_home",{4980,210,-620},{4920,220,-210},{4920,230,210},{4980,240,620}, {5250,120,-250},{5250,120,-90},{5250,120,90},{5250,120,250},60,60,1,false,true),
 cinema("goal_mouth_sweep_away",{-4980,210,620},{-4920,220,210},{-4920,230,-210},{-4980,240,-620}, {-5250,120,250},{-5250,120,90},{-5250,120,-90},{-5250,120,-250},60,60,1,false,true),
 cinema("penalty_mark_push_home",{4150,210,0},{4380,210,0},{4620,220,0},{4850,230,0}, {5250,120,0},{5250,120,0},{5250,120,0},{5250,120,0},58,60,1,false,true),
 cinema("penalty_mark_push_away",{-4150,210,0},{-4380,210,0},{-4620,220,0},{-4850,230,0}, {-5250,120,0},{-5250,120,0},{-5250,120,0},{-5250,120,0},58,60,1,false,true),
 cinema("halfway_line_crossing",{0,260,-3350},{0,290,-1117},{0,290,1117},{0,260,3350}, {0,40,-2650},{0,40,-417},{0,40,1817},{0,40,4050},58,58,1.25f,false,true),
 cinema("halfway_line_return",{0,260,3350},{0,290,1117},{0,290,-1117},{0,260,-3350}, {0,40,2650},{0,40,417},{0,40,-1817},{0,40,-4050},58,58,1.25f,false,true),
 // Both circular shots remain INSIDE the 9.15m centre circle for a full turn.
 {"centre_circle_inner_orbit",{700,260,0},{},{},{0,60,0},{},{},58,{}, {},0,1,false,false,false,MotionKind::CircleOrbit},
 {"centre_circle_full_turn",{0,260,0},{2200,0,0},{},{0,60,0},{},{},60,{}, {},0,1,false,false,false,MotionKind::CircleTurn},
 cinema("crossbar_sweep_home",{4950,310,-500},{4950,320,-170},{4950,320,170},{4950,310,500}, {5250,244,-250},{5250,244,-90},{5250,244,90},{5250,244,250},56,56,1,false,true),
 cinema("crossbar_sweep_away",{-4950,310,500},{-4950,320,170},{-4950,320,-170},{-4950,310,-500}, {-5250,244,250},{-5250,244,90},{-5250,244,-90},{-5250,244,-250},56,56,1,false,true),
 cinema("goal_front_arc",{5000,380,-1050},{4000,650,-700},{4000,650,700},{5000,380,1050}, {5250,140,0},{5250,140,0},{5250,140,0},{5250,140,0},56,56,1,false,true),
 cinema("goal_low_crane",{5000,190,620},{4950,300,250},{4650,850,-250},{4400,1200,-650}, {5250,120,0},{5250,140,0},{5250,170,0},{5250,200,0},58,54,1,false,true),
 // Full ellipse outside the stands, looking inward throughout the circuit.
 {"stadium_exterior_orbit",{11000,10800,9500},{},{},{0,50,0},{},{},56,{}, {},0,1.6f,false,true,false,MotionKind::ExteriorOrbit,10000}
};
inline constexpr unsigned motionCount=sizeof motions/sizeof motions[0];
static_assert(motionCount<64,"The shot mask must fit uint64_t");
inline constexpr uint64_t allMotionsMask=(uint64_t{1}<<motionCount)-1;
inline float duration(unsigned index,float base){
 const auto& m=motions[index%motionCount];const float length=std::clamp(base,20.f,120.f)*m.durationScale;
 return m.kind==MotionKind::ExteriorOrbit?std::clamp(length,80.f,150.f):std::clamp(length,20.f,180.f);
}
inline bool available(unsigned index,float heightLimit){const auto& m=motions[index%motionCount];return !m.exterior||heightLimit>=m.minimumHeight;}
// Ten-percent acceleration/deceleration ramps, with nearly constant cruise.
// A global smoothstep would make a full exterior circuit too fast mid-shot.
inline float orbitProgress(float progress){
 const float p=std::clamp(progress,0.f,1.f),edge=.1f;
 if(p<edge){const float u=p/edge;return edge*(u*u*u-.5f*u*u*u*u)/(1-edge);}
 if(p>1-edge){const float u=(1-p)/edge;return 1-edge*(u*u*u-.5f*u*u*u*u)/(1-edge);}
 return (p-edge*.5f)/(1-edge);
}
inline Vec bezier(Vec a,Vec b,Vec c,float t){return a*((1-t)*(1-t))+b*(2*(1-t)*t)+c*(t*t);}
inline Vec bezier(Vec a,Vec b,Vec c,Vec d,float t){const float u=1-t;return a*(u*u*u)+b*(3*u*u*t)+c*(3*u*t*t)+d*(t*t*t);}
inline Pose sample(unsigned index,float progress,float heightLimit=11000,float scale=1){
 const auto& m=motions[index%motionCount];const float t=smooth(progress);
 Pose p=m.cubic?Pose{bezier(m.a,m.b,m.c,m.d,t),bezier(m.ta,m.tb,m.tc,m.td,t),m.fov+(m.endFov-m.fov)*t}:Pose{bezier(m.a,m.b,m.c,t),bezier(m.ta,m.tb,m.tc,t),m.fov};
 if(m.kind==MotionKind::CircleOrbit){const float angle=t*6.28318530718f;p.eye={std::cos(angle)*m.a.x,m.a.y,std::sin(angle)*m.a.x};p.target=m.ta;}
 if(m.kind==MotionKind::CircleTurn){const float angle=t*6.28318530718f;p.eye=m.a;p.target={std::cos(angle)*m.b.x,m.ta.y,std::sin(angle)*m.b.x};}
 if(m.kind==MotionKind::ExteriorOrbit){const float angle=orbitProgress(progress)*6.28318530718f;p.eye={std::cos(angle)*m.a.x,m.a.y,std::sin(angle)*m.a.z};p.target=m.ta;}
 scale=std::clamp(scale,.6f,1.f);p.eye.x*=scale;p.eye.z*=scale;
 p.eye.y=std::clamp(p.eye.y,180.f,std::clamp(heightLimit,1000.f,14000.f));return p;
}
inline bool matrix(const Pose& p,float* out){
 Vec back=p.eye-p.target;if(!unit(back))return false;
 Vec right=cross({0,1,0},back);if(!unit(right))return false;
 const Vec up=cross(back,right);const Vec rows[]={right,up,back,p.eye};
 for(unsigned i=0;i<4;++i){out[i*4]=rows[i].x;out[i*4+1]=rows[i].y;out[i*4+2]=rows[i].z;out[i*4+3]=i==3?1.f:0.f;}return true;
}
inline Pose blend(const Pose& a,const Pose& b,float weight){
 return {mix(a.eye,b.eye,weight),mix(a.target,b.target,weight),a.fov+(b.fov-a.fov)*weight};
}
}
