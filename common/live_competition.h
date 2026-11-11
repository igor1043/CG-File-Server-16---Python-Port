#ifndef FIFA_LIVE_COMPETITION_H
#define FIFA_LIVE_COMPETITION_H
#include "competition_identity.h"
#include "../career_native/src/core/fce_model.h"

/* A saved career can retain a different object numbering from compobj.txt.
 * Translate through its owned FCE snapshot before selecting a 3D package. */
static inline const FceCompNode *comp_live_node(const FceModel *model,int id) {
    if(!model || model->node_count>65536)return nullptr;
    for(size_t i=0;i<model->node_count;++i)if(model->nodes[i].id==id)return &model->nodes[i];
    return nullptr;
}
static inline const FceCompNode *comp_live_ancestor(const FceModel *model,int id,int type) {
    for(unsigned hop=0;hop<64;++hop){
        const auto *node=comp_live_node(model,id);if(!node)return nullptr;
        if(node->type==type)return node;
        if(node->type==3 || node->parent==id)return nullptr;
        id=node->parent;
    }
    return nullptr;
}
static inline int comp_live_stage_kind(const CompIdentityNode *node) {
    if(!node || node->type!=4)return 0;
    const char *name=node->display;
    if(strstr(name,"Setup"))return FCE_STAGE_SETUP;
    if(strstr(name,"Group") || strstr(name,"League"))return FCE_STAGE_GROUP;
    if(strstr(name,"Quarter"))return FCE_STAGE_QUARTER_FINAL;
    if(strstr(name,"Semi"))return FCE_STAGE_SEMI_FINAL;
    if(strstr(name,"Third"))return FCE_STAGE_THIRD_PLACE;
    if(strstr(name,"Round_32") || strstr(name,"Round_of_32"))return FCE_STAGE_ROUND_32;
    if(strstr(name,"Round_16") || strstr(name,"Round_of_16"))return FCE_STAGE_ROUND_16;
    if(strstr(name,"Round_1"))return FCE_STAGE_ROUND_1;
    if(strstr(name,"Round_2"))return FCE_STAGE_ROUND_2;
    if(strstr(name,"Final"))return FCE_STAGE_FINAL;
    return 0;
}
static inline int comp_live_translate(const CompIdentityIndex *index,const FceModel *model,
                                     unsigned &competition,unsigned &round) {
    if(!model || !model->nodes || !model->node_count)return 0;
    const auto *main=comp_live_ancestor(model,(int)competition,3);
    const auto *phase=round?comp_live_ancestor(model,(int)round,3):nullptr;
    if(main && phase && main->id!=phase->id)return -1;
    if(!main)main=phase;
    if(!main)return -1;
    const int installed=comp_identity_live_id(index,main->asset);
    if(!installed)return -1;
    const auto *stage=round?comp_live_ancestor(model,(int)round,4):nullptr;
    int mapped=0;
    if(stage){
        const auto *direct=comp_identity_node(index,stage->id);
        if(main->id==installed && direct && direct->parent==installed &&
           (!stage->stage_kind || comp_live_stage_kind(direct)==stage->stage_kind))mapped=direct->id;
        else if(stage->stage_kind>0)for(unsigned i=0;i<index->count;++i){
            const auto *candidate=&index->nodes[i];
            if(candidate->parent==installed && comp_live_stage_kind(candidate)==stage->stage_kind){
                if(mapped){mapped=0;break;}mapped=candidate->id;
            }
        }
    }
    competition=(unsigned)installed;round=(unsigned)mapped;return 1;
}
static inline int comp_live_current(const CompIdentityIndex *index,unsigned &competition,unsigned &round) {
    if(!competition && !round)return 0;
    const HMODULE core=GetModuleHandleA("dinput8.dll");if(!core)return 0;
    using Acquire=void*(WINAPI*)();using Model=const FceModel*(WINAPI*)(const void*);using Release=void(WINAPI*)(void*);
    auto acquire=(Acquire)GetProcAddress(core,"Fifa16CareerAcquireCachedSnapshot");
    /* Older cores expose only the original API. With the new API present,
     * an absent cached snapshot must never trigger a scene-thread registry call. */
    if(!acquire)acquire=(Acquire)GetProcAddress(core,"Fifa16CareerAcquireSnapshot");
    auto model=(Model)GetProcAddress(core,"Fifa16CareerGetSnapshotModel");
    auto release=(Release)GetProcAddress(core,"Fifa16CareerReleaseSnapshot");
    if(!acquire || !model || !release)return 0;
    void *snapshot=acquire();if(!snapshot)return 0;
    const int result=comp_live_translate(index,model(snapshot),competition,round);
    release(snapshot);return result;
}
#endif
