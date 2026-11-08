#pragma once
#include <cstring>
namespace career_background {
enum class Mode { Image, Stadium, DressingRoom };
inline Mode parse(const char* value,bool legacyEnabled){
 if(value&&!std::strcmp(value,"image"))return Mode::Image;
 if(value&&!std::strcmp(value,"stadium"))return Mode::Stadium;
 if(value&&!std::strcmp(value,"dressing_room"))return Mode::DressingRoom;
 return legacyEnabled?Mode::Stadium:Mode::Image;
}
inline bool wantsRoom(Mode mode,bool hub,bool careerResolved,unsigned club,int role,bool menuScene){
 return mode==Mode::DressingRoom&&hub&&careerResolved&&club>0&&club<=2000000&&role==1&&menuScene;
}
}
