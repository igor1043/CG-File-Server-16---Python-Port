#include "native_scene_vignette.h"
#include <cassert>
#include <map>
#include <vector>
#include <limits>
#include <iostream>
struct Memory {
 std::map<uintptr_t,std::vector<unsigned char>> regions;unsigned writes=0;
 void make(uintptr_t at,size_t size){regions[at].resize(size);}
 bool read(uintptr_t at,void* out,size_t size){auto i=regions.upper_bound(at);if(i==regions.begin())return false;--i;if(at-i->first+size>i->second.size())return false;memcpy(out,i->second.data()+at-i->first,size);return true;}
 bool write(uintptr_t at,const void* in,size_t size){auto i=regions.upper_bound(at);if(i==regions.begin())return false;--i;if(at-i->first+size>i->second.size())return false;memcpy(i->second.data()+at-i->first,in,size);++writes;return true;}
 template<class T>void put(uintptr_t at,T value){assert(write(at,&value,sizeof value));}
 template<class T>T get(uintptr_t at){T value{};assert(read(at,&value,sizeof value));return value;}
};
struct Fixture {
 static constexpr uintptr_t image=0x140000000,vm=0x20000,globals=0x30000,globalNodes=0x31000,render=0x40000,renderNodes=0x41000,object=0x60000,block=0x70000;
 Memory m;native_scene_vignette::Lease lens;
 Fixture(){
  m.make(image+0x3613fd0,8);m.put(image+0x3613fd0,vm);m.make(vm,256);m.put(vm+0x78,globals);m.put(vm+0x80,5);
  table(globals,globalNodes);table(render,renderNodes);
  node(globalNodes,0x50000,"gRenderObj",render,5);node(renderNodes,0x50100,"postfx_vignette",object,2);
  m.make(object,40);m.put(object,image+0x221c420);m.put(object+32,block);profile(block,.2f);m.writes=0;
 }
 void table(uintptr_t at,uintptr_t nodes){m.make(at,64);m.put(at+8,uint8_t(5));m.put(at+32,nodes);m.make(nodes,40);}
 void node(uintptr_t at,uintptr_t text,const char* name,uintptr_t value,int type){m.make(text,64);m.put(text+16,strlen(name));m.write(text+24,name,strlen(name));m.put(at,value);m.put(at+8,type);m.put(at+16,text);m.put(at+24,4);}
 void profile(uintptr_t at,float alpha){m.make(at,144);for(unsigned i=0;i<3;++i){m.put(at+i*48,2.f);m.put(at+i*48+8,1.25f);m.put(at+i*48+16,.5f);m.put(at+i*48+20,.5f);m.put(at+i*48+24,.5f);m.put(at+i*48+44,alpha);}}
 void state(unsigned owner,bool show,uint64_t now){lens.state(image,owner,show,now,[&](uintptr_t a,void* b,size_t n){return m.read(a,b,n);},[&](uintptr_t a,const void* b,size_t n){return m.write(a,b,n);});}
 float alpha(unsigned i=0,uintptr_t at=block){return m.get<float>(at+i*48+44);}
};
int main(){
 {Fixture f;const auto before=f.m.regions;f.state(1,true,1000);assert(f.lens.captured&&f.m.writes==3);
  for(unsigned i=0;i<3;++i)assert(f.alpha(i)==0);
  // Every byte besides the three opacity scalars must remain exactly intact.
  auto actual=f.m.regions;for(unsigned i=0;i<3;++i)memcpy(actual[Fixture::block].data()+i*48+44,before.at(Fixture::block).data()+i*48+44,4);assert(actual==before);
  f.state(2,true,1001);f.state(1,false,1002);assert(f.alpha()==0&&f.lens.captured);
  f.state(2,false,1003);for(unsigned i=0;i<3;++i)assert(f.alpha(i)==.2f);assert(!f.lens.captured);
 }
 {Fixture f;f.state(2,true,1000);f.m.put(Fixture::block+44,.37f);f.state(2,true,1001);assert(f.alpha()==0);f.state(2,false,1002);assert(f.alpha()==.37f);}
 {Fixture f;f.state(1,true,1000);f.profile(0x80000,.6f);f.m.put(Fixture::object+32,uintptr_t(0x80000));const auto old=f.m.regions[Fixture::block];f.state(1,true,1001);assert(f.alpha(0,0x80000)==0);f.state(1,false,1002);assert(f.alpha(0,0x80000)==.6f&&f.m.regions[Fixture::block]==old);}
 {Fixture f;f.m.put(Fixture::object,uintptr_t(1));f.m.writes=0;f.state(1,true,1000);assert(!f.lens.captured&&!f.m.writes);}
 {Fixture f;f.m.put(Fixture::block+44,std::numeric_limits<float>::quiet_NaN());f.m.writes=0;f.state(2,true,1000);assert(!f.lens.captured&&!f.m.writes);}
 {Fixture f;f.m.put(Fixture::vm+0x80,0);f.m.writes=0;f.state(2,true,1000);assert(!f.lens.captured&&!f.m.writes);f.state(0,true,1001);f.state(3,true,1001);assert(!f.m.writes);}
 {Fixture f;f.profile(Fixture::block,0);f.m.writes=0;f.state(2,true,1000);assert(!f.m.writes);f.state(2,false,1001);assert(f.alpha()==0);}
 std::cout<<"PASS native vignette: exact three alpha fields, shared room/gallery ownership, live profile reload, restoration and invalid-object guards; all other bytes unchanged\n";
}
