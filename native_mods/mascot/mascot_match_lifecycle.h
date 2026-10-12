#pragma once
#include <stdint.h>
// Worker-owned tracker. The render hook consumes only its atomic serial.
// Two coherent score reads are already checked by the caller; all boundaries
// must then persist for 750 ms. No Lua/resource query is added per frame.
struct MascotMatchLifecycle{
 uintptr_t key=0,pendingKey=0;
 uint64_t missingSince=0,pendingSince=0,scoreSince=0;
 int highHome=0,highAway=0,scoreHome=-1,scoreAway=-1,pendingReason=0;
 bool ready=false,returnAfterLoad=false;
 int sample(bool valid,uintptr_t nextKey,int h,int a,uint64_t now){
  if(!valid){if(ready && !missingSince)missingSince=now;return 0;}
  if(!nextKey || h<0 || a<0)return 0;
  if(missingSince && now-missingSince>=1500 && h==0 && a==0)returnAfterLoad=true;
  missingSince=0;
  if(!ready){
   ready=true;key=nextKey;scoreHome=h;scoreAway=a;scoreSince=now;
   highHome=h;highAway=a;return 1;
  }
  const bool changed=nextKey!=key;
  const bool resetScore=h==0 && a==0 && (highHome>0 || highAway>0);
  const int reason=changed?2:resetScore?3:returnAfterLoad && h==0 && a==0?4:0;
  if(reason){
   if(pendingKey!=nextKey || pendingReason!=reason){
    pendingKey=nextKey;pendingReason=reason;pendingSince=now;return 0;
   }
   if(now-pendingSince<750)return 0;
   key=nextKey;highHome=h;highAway=a;scoreHome=h;scoreAway=a;scoreSince=now;
   pendingKey=0;pendingReason=0;returnAfterLoad=false;return reason;
  }
  pendingKey=0;pendingReason=0;returnAfterLoad=false;
  if(scoreHome!=h || scoreAway!=a){scoreHome=h;scoreAway=a;scoreSince=now;}
  if(now-scoreSince>=750){if(h>highHome)highHome=h;if(a>highAway)highAway=a;}
  return 0;
 }
};
