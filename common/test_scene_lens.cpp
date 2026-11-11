#include "scene_lens.h"
#include <cassert>
#include <fstream>
#include <vector>
int main(int argc,char**argv){
 scene_lens::Lease room,trophy;std::vector<std::string>scripts;
 auto execute=[&](const char*s){scripts.emplace_back(s);return true;};
 room.update("dressing_room",true,execute);room.update("dressing_room",true,execute);assert(scripts.size()==1);
 trophy.update("trophy_room",true,execute);room.update("dressing_room",false,execute);trophy.update("trophy_room",false,execute);assert(scripts.size()==4);
 for(const auto&s:scripts){
  assert(s.find("PostFX_Vignette")!=s.npos&&s.find("PostFX_Grain")!=s.npos);
  for(const char*depthEffect:{"PostFX_DOF","PostFX_Rectilinear","PostFX_MotionBlur"})assert(s.find(depthEffect)==s.npos);
 }
 scene_lens::Lease failure;failure.update("dressing_room",true,[](const char*){return false;});assert(failure.state==-1);
 scene_lens::Lease refreshed;unsigned count=0;auto refresh=[&](const char*){++count;return true;};
 refreshed.updateAt("trophy_room",true,1000,refresh);
 refreshed.updateAt("trophy_room",true,1499,refresh);assert(count==1);
 refreshed.updateAt("trophy_room",true,1500,refresh);assert(count==2);
 refreshed.updateAt("trophy_room",false,1501,refresh);
 refreshed.updateAt("trophy_room",false,9000,refresh);assert(count==3);
 if(argc>1){std::ofstream out(argv[1]);for(auto&s:scripts)out<<s<<"\n-- NEXT\n";}
}
