#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include "mascot_record_position.h"

static constexpr float mascotGoalLineBackX = 5850.0f;
static constexpr float mascotGoalLineZ = 3150.0f;
static constexpr unsigned int mascotPlacementTypes[]={1,18,0,22};
static constexpr unsigned int mascotPlacementTypeCount=4;
static unsigned int mascot_reserved_appearance(unsigned int type) { return type==1 || type==18?2u:1u; }
static unsigned int mascot_choose_placement_type(const size_t counts[4]) {
    for(unsigned int i=0;i<mascotPlacementTypeCount;++i)if(counts[i])return mascotPlacementTypes[i];
    return 23;
}

/* BatchSLE appearance records, NOT Lua prototypes: one record per placement.
 * Native 43a8bf0 reads the appearance byte at +42 BEFORE building draw lists.
 * Its position/yaw vector is +20 (43a915a, 43a9273, 43a9351). */
static size_t mascot_choose_corner(const unsigned char* records, size_t count)
{
    float best = 1.0e30f;
    size_t selected = 0;
    for (size_t i = 0; i < count; ++i) {
        float p[3]; memcpy(p, records + i * 0x50 + 0x20, sizeof(p));
        if (!isfinite(p[0]) || !isfinite(p[1]) || !isfinite(p[2]) ||
            fabsf(p[0]) > 20000 || fabsf(p[2]) > 20000) continue;
        /* Pick the placement nearest the human-approved destination. The
         * furthest-extents rule can switch to the opposite corner by stadium. */
        const float dx = p[0] + mascotGoalLineBackX, dz = p[2] - mascotGoalLineZ;
        const float score = dx * dx + dz * dz;
        if (score < best) { best = score; selected = i; }
    }
    return selected;
}

static size_t mascot_assign_one(unsigned char* records, size_t count, size_t selected,unsigned char reserved=2)
{
    size_t changed = 0;
    if (!records || !count || selected >= count) return 0;
    for (size_t i = 0; i < count; ++i) {
        unsigned char* record = records + i * 0x50;
        const bool mascot = i == selected;
        unsigned char desired = mascot ? reserved : record[0x42];
        if (!mascot && desired >= reserved) desired = (unsigned char)((i / 2) % reserved);
        if (record[0x42] != desired) {
            record[0x42] = desired;
            /* Rebuild this record's mesh/animation binding if it existed. */
            record[0x40] = record[0x41] = 0xff;
            record[0x45] = 0;
            ++changed;
        }
    }
    return changed;
}

static void mascot_position_by_goal_line(const float original[3], float target[3])
{
    memcpy(target, original, 3 * sizeof(float));
    /* Trial coordinates in centimetres, recessed behind the goal-line boards. Keep the same
     * corner regardless of the stadium's photographer placements. */
    target[0] = -mascotGoalLineBackX;
    target[2] = mascotGoalLineZ;
}

static size_t mascot_assign_none(unsigned char* records, size_t count,unsigned char reserved=2)
{
    size_t changed = 0;
    for (size_t i = 0; i < count; ++i) {
        unsigned char* record = records + i * 0x50;
        if (record[0x42] < reserved) continue;
        record[0x42] = (unsigned char)((i / 2) % reserved);
        record[0x40] = record[0x41] = 0xff;
        record[0x45] = 0;
        ++changed;
    }
    return changed;
}
