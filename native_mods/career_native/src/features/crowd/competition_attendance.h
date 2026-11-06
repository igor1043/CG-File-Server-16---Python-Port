#ifndef FIFA16_COMPETITION_ATTENDANCE_H
#define FIFA16_COMPETITION_ATTENDANCE_H
#include "international_competition.h"

typedef struct CrowdCompetitionProfile {
    const char *key;
    int asset, stage;
    int bonus_percent, minimum_percent, maximum_percent;
} CrowdCompetitionProfile;

/* Trophy identity is read from the active FCE snapshot, never an object
 * number from a different calendar. The fixture is the next actual match,
 * independent of the domestic table currently selected by the UI. */
static __inline CrowdCompetitionProfile crowd_competition_profile(
    const FceModel *model, const FceFixture *fixture)
{
    CrowdCompetitionProfile profile = {"domestic",-1,0,4,0,88};
    int root, stage;
    size_t i;
    if (!model || !fixture) {
        profile.bonus_percent=0;
        profile.maximum_percent=90;
        return profile;
    }
    root=fce_model_ancestor(model,fixture->competition_object,3);
    for (i=0;i<model->node_count;++i)
        if (model->nodes[i].id==root) {profile.asset=model->nodes[i].asset;break;}
    stage=fce_model_ancestor(model,fixture->competition_object,4);
    if(stage<0) stage=fixture->stage;
    profile.stage=fce_model_stage_kind(model,stage);
    if(root<0) {
        profile.bonus_percent=0;profile.stage=0;profile.maximum_percent=90;return profile;
    }
    /* Preseason tournaments retain their former estimate. */
    if ((profile.asset>=820 && profile.asset<=822) ||
        (profile.asset>=840 && profile.asset<=851) ||
        (profile.asset>=860 && profile.asset<=871)) {
        profile.key="preseason";profile.bonus_percent=0;
        profile.stage=0;profile.maximum_percent=90;return profile;
    }
    if(crowd_fixture_is_international(model,fixture)) {
        profile.key="international";profile.bonus_percent=14;profile.minimum_percent=68;
        if(profile.asset==1003) {
            profile.key="libertadores";profile.bonus_percent=22;profile.minimum_percent=75;
        } else if(profile.asset==1007) {
            profile.key="sudamericana";profile.bonus_percent=16;profile.minimum_percent=70;
        } else if(profile.asset==100 || profile.asset==1009) {
            profile.key="recopa";profile.bonus_percent=20;profile.minimum_percent=78;
        }
    } else {
        switch(profile.asset) {
        case 7: profile.key="brasileirao_a";profile.bonus_percent=14;profile.minimum_percent=68;break;
        case 83: case 2025:
            profile.key="brasileirao_b";profile.bonus_percent=10;profile.minimum_percent=60;break;
        case 229: profile.key="copa_brasil";profile.bonus_percent=16;profile.minimum_percent=70;break;
        case 350: profile.key="brasileirao_c";profile.bonus_percent=8;profile.minimum_percent=50;break;
        case 21: case 351: case 352: case 354: case 355: case 356:
        case 400: case 1046: case 1047:
            profile.key="brasileirao_d";profile.bonus_percent=6;profile.minimum_percent=42;break;
        case 22: case 23: case 25:
            profile.key="estadual";profile.bonus_percent=7;profile.minimum_percent=52;break;
        default: break;
        }
    }
    return profile;
}

static __inline float crowd_competition_apply(float factor,
    const CrowdCompetitionProfile *profile)
{
    int floor=profile->minimum_percent, ceiling=profile->maximum_percent;
    if(profile->stage==FCE_STAGE_FINAL) {floor=90;ceiling=90;}
    else if(profile->stage==FCE_STAGE_SEMI_FINAL) {
        floor+=8;
        if(floor<78)floor=78;
        ceiling=88;
    } else if(profile->stage==FCE_STAGE_QUARTER_FINAL || profile->stage==FCE_STAGE_ROUND_16) {
        floor+=4;
    }
    if(floor>ceiling)floor=ceiling;
    factor+=(float)profile->bonus_percent/100.0f;
    if(factor<(float)floor/100.0f)factor=(float)floor/100.0f;
    if(factor>(float)ceiling/100.0f)factor=(float)ceiling/100.0f;
    return factor;
}
#endif
