#pragma once
#include <cstdint>
#include <cstring>
#include <initializer_list>

// Versioned POD shared by the two native modules. No COM ownership or STL
// object crosses the module boundary; the receiver retains its own references.
namespace room_shadow_bridge {
enum Flags:unsigned {Structure=1,Background=2,Overlay=4,FloorOnly=8,TextureOnly=16,Gallery=32};
enum Owner:unsigned {DressingRoom=1,TrophyGallery=2};
struct Submission {
 uint32_t size=sizeof(Submission),version=3,club=0,generation=0;
 uint64_t object=0,frame=0;uint32_t instance=0,reserved=0;
 void* context=nullptr;float model[16]{},viewProjection[16]{};
};
struct Diagnostics {
 uint32_t size=sizeof(Diagnostics),version=1,owner=0,meshes=0,instances=0;
 uint32_t shadowFrames=0,shadowBuilds=0,shadowFailures=0,reflectionFrames=0,reflectionFailures=0,reflectionTargets=0;
};
inline bool depthCaster(const char* key,bool alpha){
 if(!key||alpha)return false;
 for(auto prefix:{"loading_","plate_","number_","name_","club_crest"})if(!std::strncmp(key,prefix,std::strlen(prefix)))return false;
 return true;
}
inline bool caster(const char* key,bool alpha){
 if(!key||alpha)return false;
 auto prefix=[&](const char* value){return !std::strncmp(key,value,std::strlen(value));};
 // Opaque room components cast by default. Floor/ceiling, artwork, alpha
 // decals and the outer shell are omitted; furniture and display frames must
 // not depend on a hand-maintained whitelist of individual material names.
 const char* excluded[]={"role_floor_","role_ceiling_",
  "v3_ceiling_","v3_floor_","v3_image_","v3_feature_","v3_corner_",
  "interior_secondary_wall_","interior_hydration_wall","interior_hydration_lower",
  "interior_hydration_header","interior_hydration_details","interior_signs",
  "interior_graphic","interior_mural","interior_light","club_crest",
  "plate_","number_","name_","floor_","ceiling_","loading_"};
 for(auto group:excluded)if(prefix(group))return false;
 if(!std::strcmp(key,"role_neutral_0")||!std::strcmp(key,"role_primary_1"))return false;
 if(!std::strcmp(key,"v3_bay_light")||!std::strcmp(key,"v3_joinery_light"))return false;
 return true;
}
}
