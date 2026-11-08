#pragma once
#include <cstdint>
#include "game_framing.h"
namespace fp {
struct CareerTarget {bool valid=false;Vec goal{};};
class CareerTargetReference {
 uintptr_t owner=0;int selected=-1,side=-1;
public:
 void reset(){owner=0;selected=side=-1;}
 CareerTarget update(uintptr_t context,int subject,int nativeSubject,int nativeTeam,int nativePitchSide,float halfLength){
  if(context!=owner||subject!=selected){owner=context;selected=subject;side=-1;}
  if(!context||subject<0||subject>=46||nativeSubject<0||nativeSubject>=46||nativeTeam<0||nativeTeam>1||
     (nativePitchSide!=1&&nativePitchSide!=-1)||!std::isfinite(halfLength)||halfLength<4000.f||halfLength>7500.f)return {};
  // The native Professional camera stores Player.TeamSide at +A08 and that
  // team's defended pitch side at +A04. It derives this from HomeTeamPitchSide
  // in BCEngine +8780F..87833. Never infer the side from dribble/head direction.
  if(subject==nativeSubject)side=nativeTeam;
  if(side<0)return {};
  const int homePitchSide=nativeTeam==0?nativePitchSide:-nativePitchSide;
  const int defendedSide=side==0?homePitchSide:-homePitchSide;
  return {true,{-float(defendedSide)*halfLength,0.f,0.f}};
 }
};
}
