#pragma once
#include <cstdint>
#include <cstring>
namespace extra {

inline bool stoppedScenePhase(int phase){return phase==14||phase==6||phase==4;}

inline bool nativeReactionCue(const char* name,bool goalKick){
 return name&&(!std::strcmp(name,"emotion_shot_missed")||
               !std::strcmp(name,"package_throwin")||
               (goalKick&&!std::strcmp(name,"emotion")));
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
