#include "scene_startup.h"
#include <cassert>
#include <iostream>
int main(){
 scene_startup::Gate gate;scene_startup::Sample s;
 s.club=112893;s.epoch=2;s.service=1;s.registry=2;s.routeRequired=true;
 unsigned props=0,cameras=0,refreshes=0;
 auto frame=[&](uint64_t t){if(gate.allow(s,t)){++props;++cameras;++refreshes;}};
 // Recorded crash ordering: Hub visible before its career context/stadium.
 s.phase=2;for(unsigned t=100;t<1600;t+=16)frame(t);assert(!props&&!cameras&&!refreshes);
 s.context=true;s.routeCurrent=true;s.loaderIdle=false;for(unsigned t=1600;t<4000;t+=16)frame(t);assert(!props);
 s.loaderIdle=true;for(unsigned t=4000;t<5000;t+=16)frame(t);assert(!props&&gate.reason==3);
 s.phase=3;frame(5000);frame(5749);assert(!props);frame(5750);assert(props==1&&cameras==1&&refreshes==1);
 // A different save/club/route must pass its own native readiness again.
 s.club=1043;s.epoch=3;s.routeCurrent=false;frame(6000);assert(props==1);
 s.routeCurrent=true;s.request=2;frame(6500);frame(7249);assert(props==1);frame(7250);assert(props==2);
 s.loaderIdle=false;frame(7300);assert(props==2);s.loaderIdle=true;frame(7400);frame(8150);assert(props==3);
 // Static backgrounds/missing optional frontend still require native idle.
 gate.reset();s.routeRequired=false;s.phase=0;assert(!gate.allow(s,9000));assert(gate.allow(s,9750));
 std::cout<<"PASS: no engine allocations, Lua/camera takeover or background refresh during native career/stadium handoff\n";
}
