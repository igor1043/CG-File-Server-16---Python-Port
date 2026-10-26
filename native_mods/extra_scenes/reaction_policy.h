#pragma once
#include <cstdint>
#include <cstring>
namespace extra {

inline bool stoppedScenePhase(int phase){return phase==14||phase==6||phase==4;}

inline bool nativeCutCamera(const char* name){
 if(!name||!name[0])return false;
 // These are native broadcast lenses in fifacamera.dat. Gameplay/blank or
 // unknown views cannot prove that a presentation camera was selected.
 return !std::strncmp(name,"Iso ",4)||!std::strncmp(name,"High Corner ",12)||
        !std::strncmp(name,"Handheld",8)||!std::strncmp(name,"Manager_",8);
}

enum class CueKind {None,MissedShot,ThrowIn,GoalKick,Corner};
inline CueKind nativeCueKind(const char* name,bool goalKick=false,bool corner=false){
 if(!name)return CueKind::None;
 if(!std::strcmp(name,"package_throwin"))return CueKind::ThrowIn;
 if(!std::strcmp(name,"package_gk_unintentional_endplay"))return CueKind::GoalKick;
 if(!std::strcmp(name,"package_cornerkick_unintentional_endplay")||
    !std::strcmp(name,"package_cornerkick_unintentional_endplay_goalkeeper_rush"))return CueKind::Corner;
 if(!std::strcmp(name,"emotion_shot_missed"))return corner?CueKind::Corner:goalKick?CueKind::GoalKick:CueKind::MissedShot;
 if(!std::strcmp(name,"emotion"))return goalKick?CueKind::GoalKick:corner?CueKind::Corner:CueKind::None;
 return CueKind::None;
}
inline bool nativeReactionCue(const char* name,bool goalKick,bool corner=false){
 return nativeCueKind(name,goalKick,corner)!=CueKind::None;
}
inline const char* cueName(CueKind kind){
 switch(kind){
  case CueKind::ThrowIn:return "throwin";
  case CueKind::GoalKick:return "goalkick";
  case CueKind::Corner:return "corner";
  case CueKind::MissedShot:return "missed_shot";
  default:return "none";
 }
}
inline bool nativeCutAllowed(int phase,const char* camera,CueKind cue,bool reserved,bool match,bool replay){
 return reserved&&match&&!replay&&stoppedScenePhase(phase)&&nativeCutCamera(camera)&&cue!=CueKind::None;
}
// A reaction package can hand its camera to an emotion graph in the SAME
// stoppage. Keep the chosen subject through that handoff, never another actor.
// This does not queue a graph, extend its lifetime, or take a gameplay lens.
inline bool nativeCutContinuation(int phase,const char* camera,const char* graph,bool reserved,bool match,bool replay){
 if(!reserved||!match||replay||!stoppedScenePhase(phase)||!nativeCutCamera(camera)||!graph)return false;
 return nativeCueKind(graph)!=CueKind::None||!std::strcmp(graph,"emotion");
}
// One decision per stoppage, even if MUSE repeats the package with a new
// temporary context. A pause/replay is not another stoppage or a fresh roll.
class StoppageLatch {
 uint64_t fixture_=0,liveSince_=0;
 bool claimed_=false;
public:
 void reset(){fixture_=liveSince_=0;claimed_=false;}
 void observe(uint64_t fixture,bool live,bool outside,uint64_t now){
  if(outside||!fixture){reset();return;}
  if(fixture_!=fixture){reset();fixture_=fixture;}
  if(!live){liveSince_=0;return;}
  if(!liveSince_)liveSince_=now;
  if(now>=liveSince_&&now-liveSince_>=1000)claimed_=false;
 }
 bool claim(){if(claimed_)return false;claimed_=true;liveSince_=0;return true;}
 bool claimed()const{return claimed_;}
};
inline uint64_t actorSceneIdentity(uint64_t renderer,uint32_t generation,uint32_t home){
 return renderer^(static_cast<uint64_t>(generation)<<32)^static_cast<uint64_t>(home)*0x9e3779b97f4a7c15ull;
}
enum class ReactionDecision {Wait,Discard,Queue};
struct ReactionWindow {
 uint64_t now=0;
 bool valid=false,enabled=false,stopped=false,live=false,outside=false;
 bool originalReaction=false,slotAvailable=false;
};
inline ReactionDecision reactionDecision(uint64_t began,const ReactionWindow& w){
 if(!w.valid||!w.enabled||w.outside||w.now<began||w.now-began>20000||
    (w.live&&w.now-began>1000))return ReactionDecision::Discard;
 if(!w.stopped||w.originalReaction||!w.slotAvailable)return ReactionDecision::Wait;
 return ReactionDecision::Queue;
}
inline int weightedActor(uint32_t seed,unsigned coach,unsigned mascot){
 if(!coach&&!mascot)return -1;
 const uint64_t total=static_cast<uint64_t>(coach)+mascot;
 return static_cast<uint64_t>(seed)%total<coach?0:1;
}
inline bool reactionChance(uint32_t serial,unsigned chance){return (serial*2654435761u)%100<chance;}
}
