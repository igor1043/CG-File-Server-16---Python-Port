#include "../native_mods/extra_scenes/scene_director.h"
#include "../native_mods/extra_scenes/scene_math.h"
#include "../native_mods/extra_scenes/scene_actor_api.h"
#include "../native_mods/extra_scenes/scene_tracking.h"
#include "../native_mods/extra_scenes/reaction_policy.h"
#include "../native_mods/extra_scenes/scene_readiness.h"
#include <cassert>
#include <cstdio>
using namespace extra;
static Input input(uint64_t now,Window w,bool preview=false){Input in;in.now=now;in.fixture=123;in.window=w;in.preview=preview;in.chance=100;in.cooldown=0;return in;}
int main(){
 {
  Actor actor{{0,0,-3600},{0,170,-3600},{0,0,1},195};ActorReadiness gate;
  gate.observe(42,1,1000,&actor);gate.observe(42,1,1200,&actor);assert(!gate.ready(1200));
  gate.observe(42,2,1210,&actor);gate.observe(42,3,1220,&actor);assert(gate.ready(1220));
  assert(!gate.ready(1421));
  gate.observe(43,4,1230,&actor);assert(!gate.ready(1230));
  gate.observe(43,5,1330,&actor);gate.observe(43,6,1430,&actor);assert(gate.ready(1430));
  actor.root.x+=200;actor.head.x+=200;gate.observe(43,7,1440,&actor);assert(!gate.ready(1440));
  gate.observe(43,8,1450,nullptr);assert(!gate.ready(1450));
  assert(sceneOpportunity(true,false,1,1,45000,1,0));
  assert(!sceneOpportunity(false,false,1,1,45000,1,100));
  assert(!sceneOpportunity(false,false,50000,1,45000,1,0));
  assert(sceneOpportunity(false,false,50000,1,45000,1,100));
 }
 assert(stoppedScenePhase(4)&&stoppedScenePhase(6)&&stoppedScenePhase(14));
 assert(!stoppedScenePhase(15)&&!stoppedScenePhase(5)&&!stoppedScenePhase(-1));
 assert(nativeReactionCue("emotion_shot_missed",false));
 assert(nativeReactionCue("emotion",true));
 assert(nativeReactionCue("package_throwin",false));
 assert(!nativeReactionCue("package_crowdchant_throwin",false)); // Preserve the crowd cut.
 assert(!nativeReactionCue("emotion",false)); // Generic reactions elsewhere cannot arm an extra.
 assert(!nativeReactionCue("emotion_foul",true));
 assert(!nativeReactionCue(nullptr,true));
 {
  ReactionWindow w{10000,true,true,true,false,false,true,false};
  assert(reactionDecision(9000,w)==ReactionDecision::Wait);
  w.slotAvailable=true;assert(reactionDecision(9000,w)==ReactionDecision::Wait);
  w.originalReaction=false;assert(reactionDecision(9000,w)==ReactionDecision::Queue);
  w.outside=true;assert(reactionDecision(9000,w)==ReactionDecision::Discard);
  w.outside=false;w.live=true;w.stopped=false;w.now=10001;
  assert(reactionDecision(9000,w)==ReactionDecision::Discard);
  w.now=9500;assert(reactionDecision(9000,w)==ReactionDecision::Wait);
  w.live=false;w.stopped=true;w.now=30001;
  assert(reactionDecision(9000,w)==ReactionDecision::Discard);
  w.now=10000;w.valid=false;assert(reactionDecision(9000,w)==ReactionDecision::Discard);
  w.valid=true;w.enabled=false;assert(reactionDecision(9000,w)==ReactionDecision::Discard);
  assert(weightedActor(1,0,0)==-1&&weightedActor(30,0,3)==1&&weightedActor(50,2,0)==0);
  unsigned coaches=0;for(unsigned i=0;i<400;++i)if(weightedActor(i,3,1)==0)++coaches;
  assert(coaches==300);
  for(unsigned i=0;i<1000;++i){assert(!reactionChance(i,0));assert(reactionChance(i,100));}
 }
 Director d;
 assert(!d.tick(input(100000,Window::Idle,true))); // Loading/kickoff cannot arm.
 assert(!d.tick(input(100010,Window::Live)));
 for(uint64_t n=100020;n<105000;n+=10)assert(!d.tick(input(n,Window::Native,true)));
 assert(!d.tick(input(105000,Window::Idle,true)));
 assert(d.tick(input(105510,Window::Idle,true))&&d.started);
 assert(!d.tick(input(105520,Window::Native,true))&&!d.active());
 assert(!d.tick(input(106100,Window::Idle,true))); // No resumption over same native scene.
 assert(!d.tick(input(106110,Window::Live)));
 assert(!d.tick(input(106200,Window::Native)));
 assert(!d.tick(input(106400,Window::Idle)));
 assert(d.tick(input(106910,Window::Idle)));
 assert(!d.tick(input(106920,Window::Live))&&!d.active()); // Never take a live ball.
 assert(!d.tick(input(106930,Window::Idle,true)));
 assert(d.tick(input(107500,Window::Idle,true)));
 assert(!d.tick(input(107510,Window::Outside))&&!d.active()); // Pause/replay/menu cancel.
 Input off=input(107520,Window::Idle,true);off.enabled=false;assert(!d.tick(off));
 Director cooldown;cooldown.tick(input(200000,Window::Live));cooldown.tick(input(200010,Window::Native));cooldown.tick(input(200020,Window::Idle));
 assert(cooldown.tick(input(200530,Window::Idle)));cooldown.tick(input(203000,Window::Idle));cooldown.tick(input(203010,Window::Live));cooldown.tick(input(203100,Window::Native));
 Input wait=input(203200,Window::Idle);wait.cooldown=45000;cooldown.tick(wait);wait.now=204000;assert(!cooldown.tick(wait));
 wait.preview=true;assert(cooldown.tick(wait)); // Test bypasses cooldown, never native priority.
 Director duration;duration.tick(input(300000,Window::Live));duration.tick(input(300010,Window::Native));duration.tick(input(300020,Window::Idle));
 assert(duration.tick(input(300530,Window::Idle)));
 assert(duration.tick(input(305529,Window::Idle))); // Five full seconds when the gap permits.
 assert(!duration.tick(input(305530,Window::Idle)));
 Actor coach{{-1000,0,-3700},{-1000,170,-3700},{0,0,1},195};Lens lens{700,24,120,15};Camera camera;
 assert(build(coach,lens,false,camera));assert(std::fabs(camera.eye.z)<=3250&&std::fabs(camera.eye.x)<=5150);
 {
  Camera engine;assert(exportedCamera(camera,engine));
  assert(engine.eye.z==camera.eye.z&&engine.target.z==camera.target.z);
  assert(engine.eye.x==camera.eye.x&&engine.target.x==camera.target.x);
  Vec right{engine.matrix[0],engine.matrix[1],engine.matrix[2]},up{engine.matrix[4],engine.matrix[5],engine.matrix[6]},back{engine.matrix[8],engine.matrix[9],engine.matrix[10]};
  assert(dot(cross(right,up),back)>.999f); // A rotation, not a mirrored image.
  Vec nativeHead=coach.head;
  Vec ray=nativeHead-engine.eye;unit(ray);
  Vec aimed=engine.target-engine.eye;unit(aimed);
  assert(dot(ray,aimed)>.98f); // The rendered actor stays in the same world-space lens.
 }
 Vec dir=camera.eye-coach.root;dir.y=0;unit(dir);assert(dot(dir,coach.forward)>=.70f);
 Vec back{camera.matrix[8],camera.matrix[9],camera.matrix[10]},right{camera.matrix[0],camera.matrix[1],camera.matrix[2]};
 assert(std::fabs(length(back)-1)<.001f&&std::fabs(dot(back,right))<.001f);
 const float halfHeight=std::tan(camera.fov*.5f)*camera.focus;
 assert(halfHeight>=coach.height*.58f); // Full body includes feet/head margin.
 {
  Tripod still;const Camera initial=camera;assert(still.begin(coach,initial,1000,false));
  for(uint64_t i=1;i<=300;++i){
   Actor sway=coach;const float phase=static_cast<float>(i)*.13f;
   sway.head.x+=25*std::sin(phase);sway.head.y+=20*std::cos(phase);
   sway.root.x+=5*std::sin(phase);sway.forward={.3f*std::sin(phase),0,1};
   assert(still.update(sway,1000+i*16,camera));
   assert(length(camera.eye-initial.eye)<.001f&&length(camera.target-initial.target)<.02f);
   assert(camera.fov==initial.fov);
  }
  Tripod walk;assert(walk.begin(coach,initial,1000,false));Vec lastDirection=initial.target-initial.eye;unit(lastDirection);
  for(uint64_t i=1;i<=300;++i){
   Actor moving=coach;moving.root.x+=static_cast<float>(i)*.5f;moving.head.x+=static_cast<float>(i)*.5f;
   assert(walk.update(moving,1000+i*16,camera));assert(length(camera.eye-initial.eye)<.001f);
   Vec direction=camera.target-camera.eye;unit(direction);
   const float radians=std::acos(std::clamp(dot(lastDirection,direction),-1.f,1.f));
   assert(radians<.0026f);lastDirection=direction; // 8 degrees/s with numerical margin.
  }
  assert(camera.target.x>initial.target.x+70);
  Actor relocated=coach;relocated.root.x+=1200;assert(!walk.update(relocated,6000,camera));
  Tripod turn;assert(turn.begin(coach,initial,1000,false));Actor away=coach;away.forward={0,0,-1};
  assert(turn.update(away,1016,camera));assert(length(camera.eye-initial.eye)<.001f);
  auto sampled=[&](unsigned step){Tripod t;Camera c=initial;assert(t.begin(coach,c,1000,false));
   for(unsigned ms=step;ms<=4800;ms+=step){Actor a=coach;a.root.x+=static_cast<float>(ms)*.025f;assert(t.update(a,1000+ms,c));}return c;};
  assert(length(sampled(16).target-sampled(32).target)<2.f);
  assert(build(coach,lens,true,camera));const Camera portrait=camera;Tripod close;assert(close.begin(coach,portrait,1000,true));
  Actor nod=coach;nod.head.y-=30;nod.head.x+=25;
  assert(close.update(nod,1500,camera));assert(length(camera.target-portrait.target)<.02f);
 }
 coach.forward={0,0,-1};assert(!build(coach,lens,true,camera)); // Stand-side view skipped.
 Actor mascot{{5850,0,2700},{5850,190,2700},{-1,0,0},240};lens={850,24,120,0};
 assert(build(mascot,lens,false,camera));assert(camera.eye.x<=5150&&std::fabs(camera.eye.z)<=3250);
 assert(std::tan(camera.fov*.5f)*camera.focus>=mascot.height*.58f);
 mascot.head.x=NAN;assert(!build(mascot,lens,true,camera));
 std::puts("PASS: native cuts retain priority, additive gap only, immediate live/replay/menu cancellation, one extra per stoppage, cooldown and preview guards");
 std::puts("PASS: frontal pitch-side cameras, stands rejected, full-body feet/head framing, orthonormal lens and malformed actor rejection");
 std::puts("PASS: five-second duration, planted tripod ignores head/body sway, limited smooth pans for walking, frame-rate independence, no orbit on actor turn or teleport");
}
