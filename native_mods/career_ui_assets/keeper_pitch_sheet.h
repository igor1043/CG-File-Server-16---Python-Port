#ifndef FIFA16_KEEPER_PITCH_SHEET_H
#define FIFA16_KEEPER_PITCH_SHEET_H
#include <stdint.h>
#include <string.h>

enum { KEEPER_SHEET_SIZE=0x2dc, KEEPER_SHEET_TEAM=4, KEEPER_SHEET_TEAM_KIT=8 };

/* This is a SHARED team-kit selector, used by every player in the lineup.
   The goalkeeper decodes -1 as team 262143, while the outfield branch already
   handles negative keys as automatic selection. Normalize the sentinel to
   zero so BOTH native branches choose the sheet's TeamID: GK type 2, line
   type 0. A positive packed type-2 key would dress the entire XI as keepers.
   Repair only the sentinel in a local view copy; retain valid overrides. */
static int keeper_pitch_repair(const unsigned char *source,unsigned char *copy)
{
    uint32_t team,kit;
    memcpy(&team,source+KEEPER_SHEET_TEAM,sizeof(team));
    memcpy(&kit,source+KEEPER_SHEET_TEAM_KIT,sizeof(kit));
    if(kit!=UINT32_MAX || !team || team>=0x3ffffu)return 0;
    memcpy(copy,source,KEEPER_SHEET_SIZE);
    kit=0; /* Native automatic selection; never force the shared kit to type 2. */
    memcpy(copy+KEEPER_SHEET_TEAM_KIT,&kit,sizeof(kit));
    return 1;
}
#endif
