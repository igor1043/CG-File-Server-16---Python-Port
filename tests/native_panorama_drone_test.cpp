#include "../native_mods/panorama_drone/director.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
using namespace panorama;
int main(){
 _set_error_mode(_OUT_TO_STDERR);_set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
 static_assert(motionCount==24,"Twenty-four additional shots");
 assert(eligibleCamera(1,"BC: Stadium FE 1 20.0")&&eligibleCamera(1,"BC: Stadium FE 5 2.0"));
 assert(!eligibleCamera(15,"BC: Stadium FE 1")&&!eligibleCamera(2,"BC: Stadium FE 1"));
 assert(!eligibleCamera(1,"BC: Stadium FE Step Kit Select")&&!eligibleCamera(1,"BC: StadiumPanCam_1")&&!eligibleCamera(1,"BC: Broadcast Pos")&&!eligibleCamera(1,nullptr));
 for(unsigned m=0;m<motionCount;++m){
  for(unsigned k=0;k<m;++k)assert(std::strcmp(motions[m].id,motions[k].id));
  Pose last=sample(m,0);
  for(unsigned i=0;i<=3200;++i){const auto p=sample(m,i/3200.f);float mat[16];assert(matrix(p,mat));
   assert(std::fabs(p.eye.x)<=12000&&std::fabs(p.eye.z)<=11000&&p.eye.y>=180&&p.eye.y<=11000);
   if(!motions[m].exterior)assert(std::fabs(p.eye.x)<=4500.01f&&std::fabs(p.eye.z)<=2600.01f&&p.eye.y<=5000);
   // Cross above the stand rim, never through the stand on an exterior arrival.
   if(motions[m].exterior&&(std::fabs(p.eye.x)>5500||std::fabs(p.eye.z)>3200)){
    assert(p.eye.y>=6500);
    const Vec aim=p.target-p.eye;
    const float depression=std::atan2(-aim.y,std::sqrt(aim.x*aim.x+aim.z*aim.z))*57.29577951f;
    assert(depression-p.fov*.5f>12); // Keep the upper frame looking down onto the model, away from an unmodelled horizon.
   }
   assert(p.fov>=48&&p.fov<=68);
   Vec right{mat[0],mat[1],mat[2]},up{mat[4],mat[5],mat[6]},back{mat[8],mat[9],mat[10]};
   assert(dot(cross(right,up),back)>.999f);
   if(i){const auto d=p.eye-last.eye;const float dt=duration(m,52)/3200.f;assert(std::sqrt(dot(d,d))/dt<500.f);} // <5m/s including the long exterior approaches.
   last=p;
  }
  assert(sample(m,.5f,1200).eye.y<=1200);
  const auto full=sample(m,.5f),scaled=sample(m,.5f,11000,.6f);assert(std::fabs(scaled.eye.x-full.eye.x*.6f)<.01f);
  const auto begin=sample(m,0),nearBegin=sample(m,.0001f),end=sample(m,1),nearEnd=sample(m,.9999f);
  assert(dot(begin.eye-nearBegin.eye,begin.eye-nearBegin.eye)<.01f&&dot(end.eye-nearEnd.eye,end.eye-nearEnd.eye)<.01f);
  assert(duration(m,52)>=52&&duration(m,52)<=84);
 }
 Settings cfg;Director d;unsigned seen=0,previous=99;bool active=false;double nativeSeconds=0;float previousOpacity=0,lastProgress=0;
 for(unsigned i=0;i<260000;++i){auto r=d.tick(.01,true,cfg);
  if(!r.active)nativeSeconds+=.01;
  if(r.active&&!active){assert(r.motion!=previous);previous=r.motion;seen|=1u<<r.motion;assert(r.progress==0);}
  if(r.active!=active)assert(r.opacity==1&&previousOpacity==1); // Both sides of every cut are black.
  assert(r.opacity>=0&&r.opacity<=1);
  if(r.active){assert(r.progress>=0&&r.progress<=1);if(active)assert(r.progress>=lastProgress&&r.progress-lastProgress<=.0004f);lastProgress=r.progress;}
  active=r.active;previousOpacity=r.opacity;
 }
 assert(seen==allMotionsMask&&nativeSeconds>400);
 assert(!d.tick(.01,false,cfg).active);assert(!d.tick(.01,true,cfg).active); // Fresh entry preserves initial native window.
 cfg.initial=0;cfg.mask=1u<<7;d.reset();assert(d.tick(0,true,cfg).motion==7);
 cfg.mask=allMotionsMask;d.reset();assert(d.tick(0,true,cfg).motion==12); // New arrival is the first extra, after the original window.
 // A stadium profile with a low height ceiling excludes exterior routes.
 cfg.heightLimit=3200;d.reset();unsigned interiorSeen=0;
 for(unsigned i=0;i<180000;++i){const auto r=d.tick(.02,true,cfg);if(r.active){assert(!motions[r.motion].exterior);interiorSeen|=1u<<r.motion;}}
 for(unsigned i=0;i<motionCount;++i)assert(bool(interiorSeen&(1u<<i))==!motions[i].exterior);
 cfg.mask=1u<<12;d.reset();for(unsigned i=0;i<500;++i)assert(!d.tick(.1,true,cfg).active);
 cfg.heightLimit=11000;cfg.mask=1u<<12;
 // Even very low/irregular frame rates cannot skip the fully black cut.
 for(double step:{.016,.1,.5}){Director low;bool wasActive=false;float alpha=0;
  for(unsigned i=0;i<16000;++i){const auto r=low.tick(step,true,cfg);if(r.active!=wasActive)assert(r.opacity==1&&alpha==1);alpha=r.opacity;wasActive=r.active;}
 }
 cfg.enabled=false;assert(!d.tick(.01,true,cfg).active);
 cfg.enabled=true;cfg.mask=0;assert(!d.tick(.01,true,cfg).active);
 std::puts("PASS: 24 slow cinematic routes, exterior rim clearance, gradual lens changes, 52-83s durations, low-roof exclusion, native windows, fully black cuts at high/low FPS, full rotation, exit/disable guards");
}
