#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../src/host/career_transfer_cards.h"

typedef struct { char id[32]; int visible,player; } Row;
typedef struct { int count,selected,adds,fail_add; Row rows[32]; } Provider;
static int observed_first,observed_end,observed_latest,calls;
static void *observed_owner,*observed_provider,*observed_deals;
static int row_count(void *p) { return ((Provider *)p)->count; }
static int add_row(void *p) {
    Provider *v=p;
    ++v->adds;
    if(v->fail_add) return -1;
    return v->count++;
}
static void select_row(void *p,int index) {
    Provider *v=p;
    /* Reproduce the native silent rejection which caused the three-row cap. */
    if(index>=0 && index<v->count) v->selected=index;
}
static void set_string(void *p,const char *key,const char *value) {
    Provider *v=p; Row *r=&v->rows[v->selected];
    if(!strcmp(key,"ID")) snprintf(r->id,sizeof(r->id),"%s",value);
    if(!strcmp(key,"VISIBLE")) r->visible=!strcmp(value,"TRUE");
}
static void original(void *owner,void *provider,int first,int end,void *deals,int latest)
{
    Provider *v=provider;int i,count=*(int *)deals;
    observed_owner=owner;observed_provider=provider;observed_deals=deals;
    observed_first=first;observed_end=end;observed_latest=latest;++calls;
    assert(first>=0 && end<=v->count);
    for(i=first;i<end && i-first<count;++i) {
        char id[32];
        select_row(v,i);snprintf(id,sizeof(id),"%s%d",latest ? "LASTDEAL" : "TOPDEAL",i);
        set_string(v,"ID",id);set_string(v,"VISIBLE","TRUE");
        v->rows[i].player=1000+i-first;
    }
}
static void check_range(Provider *p,int first,int visible,int latest) {
    int i;char id[32];
    for(i=0;i<10;++i) {
        snprintf(id,sizeof(id),"%s%d",latest ? "LASTDEAL" : "TOPDEAL",first+i);
        assert(!strcmp(p->rows[first+i].id,id));
        assert(p->rows[first+i].visible==(i<visible));
        if(i<visible) assert(p->rows[first+i].player==1000+i);
    }
}
int main(void)
{
    int owner=1,deals=25,order,n;
    Provider p={6,0,0,0,{{0}}};
    career_transfer_cards_publish(&owner,&p,0,3,&deals,0);assert(!calls);
    g_transfer_cards_publish=original;
    /* Missing native services retain the stock three-row behavior. */
    career_transfer_cards_publish(&owner,&p,0,3,&deals,0);
    assert(calls==1 && observed_end==3 && !p.adds);
    g_transfer_cards_row_count=row_count;g_transfer_cards_add_row=add_row;
    g_transfer_cards_select_row=select_row;g_transfer_cards_set_string=set_string;
    for(order=0;order<2;++order) {
        memset(&p,0,sizeof(p));p.count=6;deals=25;
        career_transfer_cards_publish(&owner,&p,order ? 3 : 0,order ? 6 : 3,&deals,order);
        career_transfer_cards_publish(&owner,&p,order ? 0 : 3,order ? 3 : 6,&deals,!order);
        assert(p.count==20 && p.adds==14);
        assert(observed_owner==&owner && observed_provider==&p && observed_deals==&deals);
        check_range(&p,0,10,0);check_range(&p,10,10,1);
        /* Shrinking / empty data must clear yesterday's players, and changing
         * one card must never overwrite the other card's rows. */
        for(n=0;n<=10;++n) {
            deals=n;career_transfer_cards_publish(&owner,&p,0,3,&deals,0);
            assert(observed_first==0 && observed_end==10 && observed_latest==0);
            check_range(&p,0,n,0);check_range(&p,10,10,1);
        }
        deals=0;career_transfer_cards_publish(&owner,&p,3,6,&deals,1);
        assert(observed_first==10 && observed_end==20 && observed_latest==1);
        check_range(&p,10,0,1);assert(p.adds==14);
    }
    /* Unknown native calls stay untouched, without allocations or clearing. */
    deals=0;career_transfer_cards_publish(&owner,&p,4,7,&deals,1);
    assert(observed_first==4 && observed_end==7 && p.adds==14);
    career_transfer_cards_publish(&owner,&p,0,3,&deals,2);
    assert(observed_first==0 && observed_end==3 && observed_latest==2);
    memset(&p,0,sizeof(p));p.count=6;p.fail_add=1;
    career_transfer_cards_publish(&owner,&p,3,6,&deals,1);
    assert(p.adds==1 && observed_first==3 && observed_end==6);
    puts("PASS: ten top/latest transfers; native capacity, disjoint IDs, refresh clearing and safe fallback");
    return 0;
}
