#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cassert>
#include <fstream>
#include <iostream>
#include <limits>
#include "field_prop_shadow.h"
struct Backend {
 bool available=true,loaded=true,belongs=true,binding=true;unsigned creates=0,binds=0,sets=0,hides=0;
 std::array<bool,64> visible{};std::array<fieldshadow::Matrix,64> pose{};
 bool alive(uintptr_t,const std::string&){return belongs;}
 uintptr_t create(const char*){++creates;return available?17:0;}
 bool bind(uintptr_t,const std::string&,const std::string&,const std::string&){++binds;return binding;}
 bool ready(uintptr_t){return loaded;}
 bool set(uintptr_t,unsigned slot,const fieldshadow::Matrix& m,bool show){++sets;hides+=!show;visible[slot]=show;pose[slot]=m;return true;}
 void note(const char*){}
};
int main(int argc,char**argv){
 fieldshadow::Cache<Backend> cache("stands");SceneLuaSnapshot scene{1,2};fieldshadow::Matrix poses[13];
 for(unsigned i=0;i<13;++i)poses[i]=fieldshadow::transform(-4200+i*200.f,0,3620,.2f);
 assert(cache.update(3,scene,"stand.rx3","stand_",poses,13,true));assert(cache.api.creates==1&&cache.api.binds==1&&cache.api.sets==13);
 const auto sets=cache.api.sets;for(unsigned frame=0;frame<5000;++frame)assert(cache.update(3,scene,"stand.rx3","stand_",poses,13,true));assert(cache.api.sets==sets&&cache.api.binds==1);
 poses[4]=fieldshadow::transform(4200,0,3620,1.57f);assert(cache.update(3,scene,"stand.rx3","stand_",poses,13,true));assert(cache.api.sets==sets+1&&cache.api.pose[4]==poses[4]);
 assert(!cache.update(3,scene,"stand.rx3","stand_",poses,13,false));for(bool show:cache.api.visible)assert(!show);
 assert(cache.update(3,scene,"stand.rx3","stand_",poses,13,true));
 // Reload the one owned resource when competition changes; loading never
 // leaves the previous shape's shadow visible on the pitch.
 cache.api.loaded=false;assert(!cache.update(3,scene,"cbf.rx3","cbf_",poses,13,true));assert(cache.api.creates==1&&cache.api.binds==2);
 for(bool show:cache.api.visible)assert(!show);cache.api.loaded=true;assert(cache.update(3,scene,"cbf.rx3","cbf_",poses,13,true));
 assert(cache.update(4,scene,"cbf.rx3","cbf_",poses,13,true));assert(cache.api.creates==1&&cache.api.binds==3);
 cache.api.belongs=false;assert(cache.update(5,scene,"cbf.rx3","cbf_",poses,13,true));assert(cache.api.creates==2);
 scene.globals=8;assert(cache.update(6,scene,"cbf.rx3","cbf_",poses,13,true));assert(cache.api.creates==3);
 const auto beforeMissing=cache.api.sets;assert(!cache.update(0,{},"cbf.rx3","cbf_",poses,13,false));assert(cache.object==0&&cache.api.sets==beforeMissing);
 assert(cache.update(6,scene,"cbf.rx3","cbf_",poses,13,true));assert(cache.api.creates==4);
 poses[0][12]=std::numeric_limits<float>::quiet_NaN();assert(!cache.update(6,scene,"cbf.rx3","cbf_",poses,13,true));for(bool show:cache.api.visible)assert(!show);
 fieldshadow::Cache<Backend> failure("var_cabin");failure.api.binding=false;poses[0]=fieldshadow::transform(800,2,-3800);
 assert(!failure.update(3,scene,"var.rx3","var_",poses,1,true));assert(failure.errors==1);for(unsigned i=0;i<100;++i)assert(!failure.update(3,scene,"var.rx3","var_",poses,1,true));assert(failure.api.binds==1);
 failure.api.binding=true;assert(failure.update(4,scene,"var.rx3","var_",poses,1,true));
 if(argc==2){std::ofstream script(argv[1]);script<<fieldshadow::bindScript("stands","server16_field_shadow_stands_1","data/sceneassets/standball/generic1/model.rx3","standball_generic1_");
  std::ofstream balls(std::string(argv[1])+".balls");balls<<fieldshadow::bindScript("balls","server16_field_shadow_balls_1","data/sceneassets/ball/ball_23.rx3","ball_");}
 std::cout<<"PASS native field caster lifecycle: 13 supports/balls; 5000 stable frames without reload or transform churn; moving transform; hidden entrance; resource reload; owner/VM changes; invalid pose; isolated failure\n";
}
