#pragma once
#include <string>
#include <chrono>
#include <cstdint>
namespace scene_lens {
// Use FIFA's documented Settings table. Each scene owns only its lease;
// leaving the last scene restores the user's values without touching ini files.
struct Lease {
 int state=-1;
 uint64_t nextRefresh=0;
 template<class Execute>void updateAt(const char*owner,bool enabled,uint64_t now,Execute execute){
  if(state==int(enabled)&&(!enabled||now<nextRefresh))return;
  std::string script="do local as=gSportsRNA;if as then local settings=as:GetTable('Settings');S16SceneLens=S16SceneLens or {owners={},saved={}};local s=S16SceneLens;s.owners['";
  script+=owner;script+="']=";script+=enabled?"true":"false";
  script+=";s.observed=s.observed or {};local active=false;for _,v in pairs(s.owners) do if v then active=true end end;for _,k in ipairs({'PostFX_Vignette','PostFX_Grain'}) do if active then if s.saved[k]==nil then s.saved[k]=as:GetInt(settings,k) end;if as:GetInt(settings,k)~=0 then as:SetInt(settings,k,0) end elseif s.saved[k]~=nil then if as:GetInt(settings,k)==0 then as:SetInt(settings,k,s.saved[k]) end;s.saved[k]=nil end;s.observed[k]=as:GetInt(settings,k) end end end";
  if(execute(script.c_str())){state=int(enabled);nextRefresh=now+500;}
 }
 template<class Execute>void update(const char*owner,bool enabled,Execute execute){
  const auto now=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
  updateAt(owner,enabled,uint64_t(now),execute);
 }
};
}
