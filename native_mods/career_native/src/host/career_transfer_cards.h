#ifndef CAREER_TRANSFER_CARDS_H
#define CAREER_TRANSFER_CARDS_H
#include <stdio.h>

#define CAREER_TRANSFER_CARD_ROWS 10
#define CAREER_TRANSFER_LATEST_FIRST 10
#define CAREER_TRANSFER_PROVIDER_ROWS 20
typedef void (*CareerTransferPublishFn)(void *,void *,int,int,void *,int);
typedef int (*CareerTransferRowCountFn)(void *);
typedef int (*CareerTransferAddRowFn)(void *);
typedef void (*CareerTransferSelectRowFn)(void *,int);
typedef void (*CareerTransferSetStringFn)(void *,const char *,const char *);
static CareerTransferPublishFn g_transfer_cards_publish;
static CareerTransferRowCountFn g_transfer_cards_row_count;
static CareerTransferAddRowFn g_transfer_cards_add_row;
static CareerTransferSelectRowFn g_transfer_cards_select_row;
static CareerTransferSetStringFn g_transfer_cards_set_string;

/* Both stock refresh paths sort the complete deal vector before this call.
 * Extending only the loop is insufficient: SelectRow silently rejects indices
 * outside the native provider's six rows, and the stock 0..2 / 3..5 ranges
 * overlap when expanded. Grow this provider with the engine's own AddRow API
 * on its caller thread, then give each slide a separate ten-row range.
 * The original publisher retains filtering, names, fees, badges and PARAMs. */
static int career_transfer_cards_reserve(void *provider)
{
    int count,previous;
    if(!provider || !g_transfer_cards_row_count || !g_transfer_cards_add_row ||
       !g_transfer_cards_select_row || !g_transfer_cards_set_string) return 0;
    count=g_transfer_cards_row_count(provider);
    if(count<0 || count>256) return 0;
    while(count<CAREER_TRANSFER_PROVIDER_ROWS) {
        previous=count;
        g_transfer_cards_add_row(provider);
        count=g_transfer_cards_row_count(provider);
        if(count!=previous+1) return 0;
    }
    return 1;
}

static void career_transfer_cards_publish(void *owner,void *provider,
    int first,int end,void *deals,int latest)
{
    int row;
    char id[32];
    if(!g_transfer_cards_publish) return;
    if(((latest==0 && first==0 && end==3) ||
        (latest==1 && first==3 && end==6)) &&
       career_transfer_cards_reserve(provider)) {
        first=latest ? CAREER_TRANSFER_LATEST_FIRST : 0;
        end=first+CAREER_TRANSFER_CARD_ROWS;
        /* A later refresh can contain fewer eligible deals. Publish explicit
         * hidden IDs before filling real rows so old players cannot linger. */
        for(row=first;row<end;++row) {
            snprintf(id,sizeof(id),"%s%d",latest ? "LASTDEAL" : "TOPDEAL",row);
            g_transfer_cards_select_row(provider,row);
            g_transfer_cards_set_string(provider,"ID",id);
            g_transfer_cards_set_string(provider,"VISIBLE","FALSE");
        }
    }
    g_transfer_cards_publish(owner,provider,first,end,deals,latest);
}
#endif
