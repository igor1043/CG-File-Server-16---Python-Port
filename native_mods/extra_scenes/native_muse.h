#pragma once
// Read-only scheduler view. Never queue/skip/clone/release/load native graphs.
namespace native_muse {
struct Presentation {uintptr_t graph=0;CueKind cue=CueKind::None;int category=-1;char name[96]{};};
static Presentation current(uintptr_t engine){
 Presentation out;
 const auto scene=get<uintptr_t>(engine+0x68),services=get<uintptr_t>(scene+0x10);
 if(get<uintptr_t>(services)!=bc+0x1165b0)return out;
 const auto adapter=get<uintptr_t>(services+0x50);
 if(get<uintptr_t>(adapter)!=bc+0x1166d0)return out;
 const auto impl=get<uintptr_t>(adapter+0x58);
 if(get<uintptr_t>(impl)!=bc+0x12c890)return out;
 const auto manager=get<uintptr_t>(impl+0xa0);
 if(get<uintptr_t>(manager)!=bc+0x12c300)return out;
 const auto processor=get<uintptr_t>(manager+0xb0),selected=get<uintptr_t>(processor+0x60);
 const auto first=get<uintptr_t>(processor+0x28),end=get<uintptr_t>(processor+0x30);
 if(!selected||first<0x10000||end<=first||end-first>4096||(end-first)%8)return out;
 bool member=false,goalKick=false,corner=false;
 for(auto p=first;p<end;p+=8){
  const auto task=get<uintptr_t>(p),graph=get<uintptr_t>(task+8);char name[96]{};
  if(task==selected)member=true;
  if(!read(graph+0x18,name,sizeof name-1))return Presentation{};
  goalKick=goalKick||!strcmp(name,"package_gk_unintentional_endplay");
  corner=corner||!strcmp(name,"package_cornerkick_unintentional_endplay");
 }
 if(!member)return out;
 out.graph=get<uintptr_t>(selected+8);out.category=get<int>(selected+0x18);
 if(get<uintptr_t>(out.graph)!=bc+0x12eff0||!read(out.graph+0x18,out.name,sizeof out.name-1))return Presentation{};
 out.cue=nativeCueKind(out.name,goalKick,corner);return out;
}
}
