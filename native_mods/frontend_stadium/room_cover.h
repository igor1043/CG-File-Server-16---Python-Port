#pragma once
#include "menu_page.h"
#include "../../common/scene_loading.h"
namespace frontend_stadium {
// The native background factory can run before FluxHub publishes its page.
// This only selects the photograph, never starts a scene or alters settings.
inline bool roomCoverPage(PageKind page){
 return page==PageKind::Hub||page==PageKind::IdlePanorama||page==PageKind::Menu||page==PageKind::Transition;
}
inline bool roomCoverSelected(PageKind page,bool configured,int role,bool menuScene){
 // Hub can precede CareerContext publication. Keep its photograph covered
 // until the role and selected club are known; player career keeps stadium.
 return configured&&menuScene&&roomCoverPage(page)&&(role==1||
     (role<0&&(page==PageKind::Hub||page==PageKind::IdlePanorama||page==PageKind::Transition)));
}
inline bool roomCoverReady(unsigned club,bool settled,const scene_loading::Status* state){
 return club&&settled&&state&&state->version==1&&state->size==sizeof(*state)
     &&state->visible&&state->variant==4&&state->club==club&&state->ready&&!state->error
     &&state->total&&state->loaded>=state->total;
}
// While the room prepares, its backdrop is the already loaded stadium. The
// photo only covers the native stadium reload, never the room preparation.
inline bool roomPanoramaReady(unsigned club,bool settled,unsigned loadedClub,bool sceneReady,bool validRoute){
 return club&&club==loadedClub&&settled&&sceneReady&&validRoute;
}
inline uint64_t roomCoverStamp(unsigned club,bool ready){return (uint64_t(1)<<63)|(uint64_t(club)<<1)|(ready?1u:0u);}
}
