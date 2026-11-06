#include "../../src/host/calendar_icon_identity.h"
#include "../../../common/competition_identity.h"
#include <assert.h>
int main(void) {
    static const FceCompNode saved[]={
        {1437,1361,3,1003,0},{1458,1437,4,-1,2},{1597,1596,3,229,0},
        {1702,1597,4,-1,0},{1738,1596,3,7,0},{1739,1738,4,-1,0},
        {2419,2314,3,23,0},{2430,2419,4,-1,0}};
    static CompIdentityIndex installed;
    const int roots[]={1738,1597,1437,2419},stages[]={1739,1702,1458,2430};
    const int assets[]={7,229,1003,23},ids[]={1761,1620,1460,2442};
    int i,fixture;FceCompetition result;
    installed.count=4;
    for(i=0;i<4;++i){
        CompIdentityNode *n=&installed.nodes[i];n->id=ids[i];n->type=3;
        snprintf(n->name,sizeof(n->name),"C%d",assets[i]);
        snprintf(n->display,sizeof(n->display),"TrophyName_Abbr15_%d",assets[i]);
        installed.slot[n->id]=(unsigned short)(i+1);
    }
    for(i=0;i<4;++i)for(fixture=1;fixture<65536;++fixture){
        int ref[]={roots[i],stages[i],fixture};
        assert(calendar_icon_identity(saved,8,ref,&result)==FCE_OK);
        assert(result.asset==assets[i]);
        assert(comp_identity_live_id(&installed,result.asset)==ids[i]);
    }
    {int ref[]={1738,1458,820};assert(calendar_icon_identity(saved,8,ref,&result)==FCE_CONFLICT);}
    {int ref[]={9998,9999,1738};assert(calendar_icon_identity(saved,8,ref,&result)==FCE_UNKNOWN);}
    puts("PASS: 262140 calendar references, four saved-career identities -> INI IDs; fixture IDs never choose artwork");
    return 0;
}
