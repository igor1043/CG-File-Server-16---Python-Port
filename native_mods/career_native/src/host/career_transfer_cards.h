#ifndef CAREER_TRANSFER_CARDS_H
#define CAREER_TRANSFER_CARDS_H

#define CAREER_TRANSFER_CARD_ROWS 10
typedef void (*CareerTransferPublishFn)(void *,void *,int,int,void *,int);
static CareerTransferPublishFn g_transfer_cards_publish;

/* Both stock refresh paths sort the complete deal vector before this call.
 * Only extend the exclusive end ID: the original publisher still owns record
 * filtering, vector bounds, player names, clubs, fees and component payloads.
 * LASTDEAL IDs must start at 3: the TransferInfo consumer discovers successive
 * components starting at that stock ID, independently of TOPDEAL IDs. */
static void career_transfer_cards_publish(void *owner,void *provider,
    int first,int end,void *deals,int latest)
{
    if(!g_transfer_cards_publish) return;
    if((latest==0 && first==0 && end==3) ||
       (latest==1 && first==3 && end==6))
        end=first+CAREER_TRANSFER_CARD_ROWS;
    g_transfer_cards_publish(owner,provider,first,end,deals,latest);
}
#endif
