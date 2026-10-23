#include "../native_mods/panorama_drone/director.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
using namespace panorama;
int main(){
 _set_error_mode(_OUT_TO_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
 static_assert(motionCount==39,"Thirty-nine additional shots");
 assert(eligibleCamera(1,"BC: Stadium FE 1 20.0")&&eligibleCamera(1,"BC: Stadium FE 5 2.0"));
 assert(!eligibleCamera(15,"BC: Stadium FE 1")&&!eligibleCamera(2,"BC: Stadium FE 1"));
 assert(!eligibleCamera(1,"BC: Stadium FE Step Kit Select")&&!eligibleCamera(1,"BC: StadiumPanCam_1")&&!eligibleCamera(1,"BC: Broadcast Pos")&&!eligibleCamera(1,nullptr));
 for(unsigned m=0;m<motionCount;++m){
  for(unsigned k=0;k<m;++k)assert(std::strcmp(motions[m].id,motions[k].id));
  Pose last=sample(m,0);
  for(unsigned i=0;i<=3200;++i){const auto p=sample(m,i/3200.f);float mat[16];assert(matrix(p,mat));
   const bool profile=motions[m].kind==MotionKind::ExteriorProfileOrbit;
   assert(std::fabs(p.eye.x)<=(profile?16500:12000)&&std::fabs(p.eye.z)<=(profile?14500:11000)&&p.eye.y>=180&&p.eye.y<=11000);
   if(!motions[m].exterior){
    const float maxX=motions[m].pitchEdge?5150.f:4500.01f,maxZ=motions[m].kind==MotionKind::LineTravel?3400.01f:motions[m].pitchEdge?3350.01f:2600.01f;
    assert(std::fabs(p.eye.x)<=maxX&&std::fabs(p.eye.z)<=maxZ&&p.eye.y<=5000);
   }
   // Cross above the stand rim, never through the stand on an exterior arrival.
   if(motions[m].exterior&&!profile&&(std::fabs(p.eye.x)>5500||std::fabs(p.eye.z)>3200)){
    assert(p.eye.y>=6500);
    const Vec aim=p.target-p.eye;
    const float depression=std::atan2(-aim.y,std::sqrt(aim.x*aim.x+aim.z*aim.z))*57.29577951f;
    assert(depression-p.fov*.5f>12); // Keep the upper frame looking down onto the model, away from an unmodelled horizon.
   }
   assert(p.fov>=48&&p.fov<=68);
   Vec right{mat[0],mat[1],mat[2]},up{mat[4],mat[5],mat[6]},back{mat[8],mat[9],mat[10]};
   assert(dot(cross(right,up),back)>.999f);
   if(i){const auto d=p.eye-last.eye;const float dt=duration(m,52)/3200.f;const float speedLimit=motions[m].kind==MotionKind::ExteriorOrbit||profile?1000.f:500.f;assert(std::sqrt(dot(d,d))/dt<speedLimit);}
   last=p;
  }
  assert(sample(m,.5f,1200).eye.y<=1200);
  const auto full=sample(m,.5f),scaled=sample(m,.5f,11000,.6f);assert(std::fabs(scaled.eye.x-full.eye.x*.6f)<.01f);
  const auto begin=sample(m,0),nearBegin=sample(m,.0001f),end=sample(m,1),nearEnd=sample(m,.9999f);
  assert(dot(begin.eye-nearBegin.eye,begin.eye-nearBegin.eye)<.01f&&dot(end.eye-nearEnd.eye,end.eye-nearEnd.eye)<.01f);
  const float maximum=motions[m].kind==MotionKind::ExteriorOrbit?180.f:motions[m].kind==MotionKind::ExteriorProfileOrbit?220.f:84.f;
  assert(duration(m,52)>=52&&duration(m,52)<=maximum);
 }
 Settings cfg;Director d;uint64_t seen=0;unsigned previous=99,opened=0;bool active=false;double nativeSeconds=0;float previousOpacity=0,lastProgress=0;
 for(unsigned i=0;i<motionCount*15000;++i){auto r=d.tick(.01,true,cfg);
  if(!r.active)nativeSeconds+=.01;
  if(r.active&&!active){
   assert(r.motion!=previous);previous=r.motion;
   if(opened<3)assert(r.motion==36+opened);
   if(opened<motionCount)assert(!(seen&(uint64_t{1}<<r.motion)));
   ++opened;seen|=uint64_t{1}<<r.motion;assert(r.progress==0);
  }
  if(r.active!=active)assert(r.opacity==1&&previousOpacity==1); // Both sides of every cut are black.
  assert(r.opacity>=0&&r.opacity<=1);
  if(r.active){assert(r.progress>=0&&r.progress<=1);if(active)assert(r.progress>=lastProgress&&r.progress-lastProgress<=.0004f);lastProgress=r.progress;}
  active=r.active;previousOpacity=r.opacity;
 }
 assert(seen==allMotionsMask&&nativeSeconds>400);
 assert(!d.tick(.01,false,cfg).active);assert(!d.tick(.01,true,cfg).active); // Fresh entry preserves initial native window.
 cfg.initial=0;cfg.mask=1u<<7;d.reset();assert(d.tick(0,true,cfg).motion==7);
 cfg.mask=allMotionsMask;d.reset();assert(d.tick(0,true,cfg).motion==36); // New exterior orbit opens the pack.
 cfg.mask=uint64_t{1}<<33;d.reset();assert(d.tick(0,true,cfg).motion==33); // Above the old 32-bit limit.
 // A stadium profile with a low height ceiling excludes exterior routes.
 cfg.mask=allMotionsMask;cfg.heightLimit=3200;d.reset();uint64_t interiorSeen=0;
 for(unsigned i=0;i<180000;++i){const auto r=d.tick(.02,true,cfg);if(r.active){assert(!motions[r.motion].exterior);interiorSeen|=uint64_t{1}<<r.motion;}}
 for(unsigned i=0;i<motionCount;++i)assert(bool(interiorSeen&(uint64_t{1}<<i))==!motions[i].exterior);
 cfg.mask=1u<<12;d.reset();for(unsigned i=0;i<500;++i)assert(!d.tick(.1,true,cfg).active);
 cfg.heightLimit=11000;cfg.mask=1u<<12;
 // Even very low/irregular frame rates cannot skip the fully black cut.
 for(double step:{.016,.1,.5,.7,2.,30.}){Director low;bool wasActive=false;float alpha=0;unsigned entries=0,exits=0;
  for(unsigned i=0;i<16000;++i){const auto r=low.tick(step,true,cfg);if(r.active!=wasActive){assert(r.opacity==1&&alpha==1);if(r.active)++entries;else ++exits;}alpha=r.opacity;wasActive=r.active;}
  assert(entries>0&&exits>0);
 }
 cfg.enabled=false;assert(!d.tick(.01,true,cfg).active);
 cfg.enabled=true;cfg.mask=0;assert(!d.tick(.01,true,cfg).active);
 auto index=[](const char* id){for(unsigned i=0;i<motionCount;++i)if(!std::strcmp(motions[i].id,id))return i;assert(false);return 0u;};
 for(const char* id:{"goal_mouth_sweep_home","goal_mouth_sweep_away"}){
  const auto m=index(id);const auto first=sample(m,0),last=sample(m,1);
  assert(std::fabs(first.eye.z)>366&&std::fabs(last.eye.z)>366&&first.eye.z*last.eye.z<0);
  assert(std::fabs(first.eye.x)<5250&&std::fabs(last.eye.x)<5250);
 }
 for(const char* id:{"penalty_mark_push_home","penalty_mark_push_away"}){
  const auto m=index(id);const auto first=sample(m,0),last=sample(m,1);
  assert(std::fabs(first.eye.x)==4150&&first.eye.z==0&&last.eye.z==0);
  assert(std::fabs(last.eye.x)>std::fabs(first.eye.x)&&std::fabs(last.eye.x)<5250);
 }
 for(const char* id:{"halfway_line_crossing","halfway_line_return"}){
  const auto m=index(id);const auto first=sample(m,0),last=sample(m,1);
  assert(std::fabs(first.eye.z-last.eye.z)==6700&&first.eye.x==0&&last.eye.x==0);
 }
 for(const char* id:{"centre_circle_inner_orbit","centre_circle_full_turn"}){
  const auto m=index(id);float rotation=0;Pose last=sample(m,0);
  for(unsigned i=1;i<=3200;++i){const auto p=sample(m,i/3200.f);
   assert(p.eye.x*p.eye.x+p.eye.z*p.eye.z<915.f*915.f);
   Vec a=motions[m].kind==MotionKind::CircleOrbit?last.eye:last.target-last.eye;
   Vec b=motions[m].kind==MotionKind::CircleOrbit?p.eye:p.target-p.eye;
   rotation+=std::atan2(a.x*b.z-a.z*b.x,a.x*b.x+a.z*b.z);last=p;
  }
  assert(std::fabs(rotation-6.2831853f)<.002f);
 }
 {
  const auto m=index("stadium_exterior_orbit");const auto first=sample(m,0);Pose last=first;float rotation=0;
  unsigned quadrants=0;
  for(unsigned i=1;i<=3200;++i){const auto p=sample(m,i/3200.f);
   const float ellipse=p.eye.x*p.eye.x/(11000.f*11000.f)+p.eye.z*p.eye.z/(9500.f*9500.f);
   assert(std::fabs(ellipse-1)<.0001f&&p.eye.y==10800);
   assert(std::fabs(p.eye.x)>5500||std::fabs(p.eye.z)>3200);
   assert(p.target.x==0&&p.target.y==50&&p.target.z==0);
   rotation+=std::atan2(last.eye.x*p.eye.z-last.eye.z*p.eye.x,last.eye.x*p.eye.x+last.eye.z*p.eye.z);
   quadrants|=1u<<((p.eye.x<0?1u:0u)+(p.eye.z<0?2u:0u));last=p;
  }
  assert(quadrants==15&&std::fabs(rotation-6.2831853f)<.002f&&dot(last.eye-first.eye,last.eye-first.eye)<.01f);
  assert(duration(m,20)==95&&duration(m,120)==180);
  assert(std::fabs(duration(m,52)-98.8f)<.001f);
  // The original final stop occupied 10% of 83.2s. Keep that 8.32s ramp,
  // while reducing cruise angular speed by roughly 17%.
  assert(std::fabs(duration(m,52)*exteriorOrbitRamp-8.32f)<.001f);
  const float cruiseSpeed=1/((1-exteriorOrbitRamp)*duration(m,52));
  const float previousCruise=1/(.9f*83.2f);
  assert(cruiseSpeed/previousCruise>.80f&&cruiseSpeed/previousCruise<.85f);
  assert(!available(m,9900)&&available(m,10000));
  Settings orbit;orbit.initial=0;orbit.mask=uint64_t{1}<<m;orbit.heightLimit=9900;
  Director excluded;for(unsigned i=0;i<500;++i)assert(!excluded.tick(.1,true,orbit).active);
 }
 {
  const auto m=index("stadium_horizontal_profile_orbit");const auto first=sample(m,0);Pose last=first;float rotation=0;
  unsigned quadrants=0;
  for(unsigned i=1;i<=3200;++i){const auto p=sample(m,i/3200.f);
   const float ellipse=p.eye.x*p.eye.x/(16500.f*16500.f)+p.eye.z*p.eye.z/(14500.f*14500.f);
   assert(std::fabs(ellipse-1)<.0001f&&p.eye.y==6500);
   assert(p.target.x==0&&p.target.y==2000&&p.target.z==0);
   const Vec ray=p.target-p.eye;
   const float depression=std::atan2(-ray.y,std::sqrt(ray.x*ray.x+ray.z*ray.z))*57.29577951f;
   assert(depression>14&&depression<18); // Horizontal stadium profile, rather than an overhead pitch view.
   rotation+=std::atan2(last.eye.x*p.eye.z-last.eye.z*p.eye.x,last.eye.x*p.eye.x+last.eye.z*p.eye.z);
   quadrants|=1u<<((p.eye.x<0?1u:0u)+(p.eye.z<0?2u:0u));last=p;
  }
  assert(quadrants==15&&std::fabs(rotation-6.2831853f)<.002f&&dot(last.eye-first.eye,last.eye-first.eye)<.01f);
  assert(duration(m,52)==130&&!available(m,6499)&&available(m,6500));
 }
 {
  const auto m=index("halfway_line_full_traverse");const auto first=sample(m,0),end=sample(m,1);
  assert(first.eye.x==0&&end.eye.x==0&&first.eye.z==-3400&&end.eye.z==3400);
  Pose last=first;
  for(unsigned i=1;i<=3200;++i){const auto p=sample(m,i/3200.f);
   assert(p.eye.x==0&&p.eye.y==240&&p.eye.z>=last.eye.z);
   assert(std::fabs(p.target.z-p.eye.z-700)<.002f);
   assert(p.target.y==180);last=p;
  }
  const auto a=sample(m,.25f),b=sample(m,.5f),c=sample(m,.75f);
  assert(std::fabs((b.eye.z-a.eye.z)-(c.eye.z-b.eye.z))<.01f); // Constant walking pace through the middle.
 }
 std::puts("PASS: 39 routes, slower high orbit with preserved stopping time, horizontal-profile orbit, full halfway traverse, 64-bit selection, native windows and black cuts at high/low FPS");
}
