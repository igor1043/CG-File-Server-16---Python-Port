#include "scene_loading.h"
#include <cassert>
#include <iostream>
int main(){
 scene_loading::Status s;assert(s.size==sizeof(s)&&s.version==1);
 assert(scene_loading::progress(s)<0);
 s.total=10;s.loaded=3;assert(std::abs(scene_loading::progress(s)-.3f)<.00001f);
 s.loaded=10;assert(scene_loading::progress(s)<1.f);s.ready=1;assert(scene_loading::progress(s)==1.f);
 s={};
 assert(scene_loading::secondsRemaining(s)==-1);
 s.total=100;s.elapsedMs=10000;assert(scene_loading::secondsRemaining(s)==-1);
 s.loaded=25;assert(scene_loading::secondsRemaining(s)==30);
 s.loaded=50;assert(scene_loading::secondsRemaining(s)==10);
 s.loaded=75;assert(scene_loading::secondsRemaining(s)==4);
 s.elapsedMs=100;assert(scene_loading::secondsRemaining(s)==-1);
 s.ready=1;assert(scene_loading::secondsRemaining(s)==0);
 s.ready=0;s.loaded=100;s.elapsedMs=1000;assert(scene_loading::secondsRemaining(s)==0);
 s.loaded=1;s.elapsedMs=10000000000ULL;assert(scene_loading::secondsRemaining(s)==86400);
 std::cout<<"PASS loading ETA: unknown before measured progress, proportional estimate, bounded and completed states\n";
}
