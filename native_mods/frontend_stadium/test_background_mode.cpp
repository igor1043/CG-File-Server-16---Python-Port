#include "../../common/career_background.h"
#include <cassert>
#include <cstdio>
int main(){
 using namespace career_background;
 assert(parse("",true)==Mode::Stadium&&parse("",false)==Mode::Image);
 assert(parse("image",true)==Mode::Image&&parse("stadium",false)==Mode::Stadium);
 assert(parse("dressing_room",false)==Mode::DressingRoom);
 assert(wantsRoom(Mode::DressingRoom,true,true,1043,1,true));
 assert(!wantsRoom(Mode::Stadium,true,true,1043,1,true));
 assert(!wantsRoom(Mode::Image,true,true,1043,1,true));
 assert(!wantsRoom(Mode::DressingRoom,false,true,1043,1,true));
 assert(!wantsRoom(Mode::DressingRoom,true,false,1043,1,true));
 assert(!wantsRoom(Mode::DressingRoom,true,true,0,1,true));
 assert(!wantsRoom(Mode::DressingRoom,true,true,1043,1,false));
 assert(!wantsRoom(Mode::DressingRoom,true,true,1043,0,true));
 assert(!wantsRoom(Mode::DressingRoom,true,true,1043,2,true));
 assert(wantsRoom(Mode::DressingRoom,true,true,1629,1,true));
 puts("background: legacy preferences, all three modes, club scope, manager career, gameplay and exit guards passed");
}
