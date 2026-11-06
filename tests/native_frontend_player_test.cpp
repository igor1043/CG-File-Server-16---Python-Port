#include <cassert>
#include <iostream>
#include "../native_mods/frontend_stadium/player_scene.h"
using namespace frontend_stadium;
void put(SceneContext&c,size_t offset,int value){std::memcpy(c.data()+offset,&value,4);}
int main(){
 SceneContext native{};for(size_t i=0;i<native.size();++i)native[i]=static_cast<unsigned char>(i%251);
 put(native,0xdc,2);put(native,0xfc,1);put(native,0x20,1043);put(native,0x40,158023);
 PlayerScene scene;scene.capture(native,1043,21,0);assert(scene.valid);
 SceneContext generated{};generated.fill(0x11);auto before=generated;routeContext(generated,261);before=generated;
 assert(scene.restore(generated,1043,21,0));for(size_t i=0;i<generated.size();++i)assert(generated[i]==(i<0xe8||(i>=0xfc&&i<0x100)?native[i]:before[i]));
 assert(PlayerScene::integer(generated,0xe8)==261&&PlayerScene::integer(generated,0xec)==1);
 for(auto mismatch:{0,1,2}){auto untouched=before;assert(!scene.restore(untouched,mismatch==0?567:1043,mismatch==1?22:21,mismatch==2?1:0));assert(untouched==before);}
 put(native,0x40,233605);scene.capture(native,1043,21,0);assert(scene.restore(generated,1043,21,0)&&PlayerScene::integer(generated,0x40)==233605);
 scene.capture(native,1043,21,1);assert(!scene.valid);scene.capture(native,1043,21,2);assert(scene.valid);scene.clear();assert(!scene.valid);
 for(int count:{-1,0,9,100000}){put(native,0xdc,count);scene.capture(native,1043,21,0);assert(!scene.valid);}
 std::cout<<"PASS native player scene: actor identity/selection preserved, new stadium/light retained, natural actor changes refreshed, manager/malformed/other-save contexts excluded\n";
}
