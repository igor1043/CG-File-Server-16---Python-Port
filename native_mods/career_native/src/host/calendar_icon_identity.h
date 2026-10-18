#ifndef FIFA_CALENDAR_ICON_IDENTITY_H
#define FIFA_CALENDAR_ICON_IDENTITY_H
#include "../core/fce_contracts.h"

/* CalendarCell supplies {competition object, stage object, fixture ID}.
 * Fixture IDs are a different namespace and must never index CompData nodes.
 * Resolve both object fields against ONE live career snapshot, not today's
 * on-disk CompData: a saved career may have older object numbering. */
static __inline FceResult calendar_icon_identity(const FceCompNode *nodes,size_t count,
                                                const int reference[3],FceCompetition *out) {
    FceCompetition a,b;FceResult ra,rb;
    if(!reference || !out)return FCE_INVALID;
    out->competition=out->asset=-1;
    ra=fce_resolve_competition(nodes,count,reference[0],&a);
    rb=fce_resolve_competition(nodes,count,reference[1],&b);
    if(ra==FCE_OK && rb==FCE_OK && a.competition!=b.competition)return FCE_CONFLICT;
    if(ra==FCE_OK){*out=a;return FCE_OK;}
    if(rb==FCE_OK){*out=b;return FCE_OK;}
    return FCE_UNKNOWN;
}
#endif
