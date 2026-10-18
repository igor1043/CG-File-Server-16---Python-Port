#ifndef FIFA16_KEEPER_SQUAD_BRANCH_H
#define FIFA16_KEEPER_SQUAD_BRANCH_H
#include <stddef.h>
#include <string.h>
/* Squad/formations UI, captured from FIFA16 x64 RAM, timestamp 577DE45C.
 * RBP+104 is the team and RBP+108 the shared kit selector. The goalkeeper
 * must use the same signed automatic fallback as the ten outfield rows.
 * Only the conditional opcode changes: JE -> JLE. No sheet/save is written. */
static const unsigned char keeper_squad_native[]={
    0x8b,0x9d,0x08,0x01,0x00,0x00,0x85,0xdb,0x74,0x06,0xc1,0xeb,0x0e,
    0xeb,0x07,0x72,0x8b,0x9d,0x04,0x01,0x00,0x00,0x45,0x31,0xc0,
    0x89,0xd9,0x41,0x8d,0x50,0x02
};
enum { KEEPER_SQUAD_CONDITION=8 };
/* Editable roster, a separate producer: sheet==RBP+60, condition RVA 40997A3. */
static const unsigned char keeper_roster_native[]={
    0x8b,0x5d,0x68,0x85,0xdb,0x74,0x05,0xc1,0xeb,0x0e,0xeb,0x03,
    0x8b,0x5d,0x64,0x45,0x31,0xc0,0x89,0xd9,0x41,0x8d,0x50,0x02
};
enum { KEEPER_ROSTER_CONDITION=5 };
static int keeper_squad_signature(const unsigned char *code,size_t size)
{
    unsigned char original[sizeof(keeper_squad_native)];
    if(!code || size!=sizeof(original) ||
       (code[KEEPER_SQUAD_CONDITION]!=0x74 && code[KEEPER_SQUAD_CONDITION]!=0x7e))return 0;
    memcpy(original,code,sizeof(original));original[KEEPER_SQUAD_CONDITION]=0x74;
    return !memcmp(original,keeper_squad_native,sizeof(original));
}
static int keeper_roster_signature(const unsigned char *code,size_t size)
{
    unsigned char original[sizeof(keeper_roster_native)];
    if(!code || size!=sizeof(original) ||
       (code[KEEPER_ROSTER_CONDITION]!=0x74 && code[KEEPER_ROSTER_CONDITION]!=0x7e))return 0;
    memcpy(original,code,sizeof(original));original[KEEPER_ROSTER_CONDITION]=0x74;
    return !memcmp(original,keeper_roster_native,sizeof(original));
}
#endif
