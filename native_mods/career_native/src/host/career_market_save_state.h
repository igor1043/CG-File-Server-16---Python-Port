/* File-only handoff from the committed market to the completed-save receipt.
 * No FIFA call or SQLite access is allowed on the I/O thread. */
#ifndef CAREER_MARKET_SAVE_STATE_H
#define CAREER_MARKET_SAVE_STATE_H
#include <stdio.h>
#include <string.h>
typedef struct CareerMarketSaveState {
    unsigned schema,pid,epoch,club;
    unsigned long long created,context;
    int date;
    char revision[65];
} CareerMarketSaveState;
static int career_market_save_state_read(const char *path,unsigned pid,
    unsigned long long created,unsigned epoch,CareerMarketSaveState *out)
{
    FILE *file;char line[256];unsigned lines=0;CareerMarketSaveState state={0};
    file=fopen(path,"rb");if(!file)return 0;
    while(fgets(line,sizeof(line),file)&&++lines<=12){
        if(sscanf(line,"schema=%u",&state.schema)==1)continue;
        if(sscanf(line,"pid=%u",&state.pid)==1)continue;
        if(sscanf(line,"created=%llu",&state.created)==1)continue;
        if(sscanf(line,"context=%llx",&state.context)==1)continue;
        if(sscanf(line,"epoch=%u",&state.epoch)==1)continue;
        if(sscanf(line,"date=%d",&state.date)==1)continue;
        if(sscanf(line,"club=%u",&state.club)==1)continue;
        if(!strncmp(line,"revision=",9)&&strcspn(line+9,"\r\n")==64&&strspn(line+9,"0123456789abcdef")==64)memcpy(state.revision,line+9,64);
    }
    fclose(file);
    if(lines>12||state.schema!=1||state.pid!=pid||state.created!=created
        ||state.epoch!=epoch||!epoch||!state.context||!state.club
        ||state.date<19000101||state.date>22001231||!state.revision[0])return 0;
    *out=state;return 1;
}
#endif
