#define CAREER_JOBS_TEST
#include "career_jobs_runtime.c"
#include <assert.h>
Profile mocked_profile;
static unsigned char manager_data[0x188];
static unsigned char menu_data[0x1350];
int mocked_hub=1;
static int contracts;
static int native_rows[64][8],mails,date=20260409,reenter,withdrawals,last_archived;
static int *active_offer(void) {return (int *)(manager_data+0x158);}
static unsigned char fake_menu(void *menu,int event)
{
    assert(menu==menu_data && event==-9911);
    assert(mocked_profile.club==1043 && active_offer()[0]>0 && active_offer()[10]==-1);
    assert(menu_data[0x20] && !menu_data[0x10]);
    menu_data[0x10]=1;*(uintptr_t *)(menu_data+0x18)=(uintptr_t)manager_data;
    ++contracts;return 1;
}
static void clear_offer(void)
{
    int i;for(i=0;i<11;++i)active_offer()[i]=-1;
    active_offer()[7]=0;
}
static void fake_gather(void *source,int team,int seed,int *record)
{
    (void)source;(void)seed;memset(record,0,40);record[4]=team;record[2]=7;record[7]=2;record[9]=3;record[8]=1;
    if(team==9999)record[4]=-1;
}
static void fake_withdraw(void *manager,int team)
{
    assert(manager==manager_data && active_offer()[0]==team);
    last_archived=team;++withdrawals;
}
static void fake_add(void *manager,const int *record,int league)
{
    uintptr_t end=*(uintptr_t *)((unsigned char *)manager+0xe0);int *row=(int *)end;
    row[0]=record[4];row[1]=league;row[2]=record[2];row[3]=record[7];row[4]=record[9];row[5]=record[8];row[6]=-1;row[7]=10000;
    *(uintptr_t *)((unsigned char *)manager+0xe0)=end+32;
}
static void fake_inform(void *manager,int *offer,unsigned char browse)
{
    assert(manager==manager_data && browse==1 && offer[0]>0 && offer[1]>0 && offer[7]==10000);
    assert(offer[8]==-1 && offer[9]==-1 && offer[10]==-1);
    assert(shared->completed==shared->sequence && shared->status==0);
    offer[6]=date;++mails;
    if(reenter)process_current();
}
static void failed_inform(void *manager,int *offer,unsigned char browse)
{
    (void)manager;(void)offer;(void)browse;
}
static void request(int seq,int team,int league)
{
    shared->registry=mocked_profile.registry;shared->context=mocked_profile.context;
    shared->request_epoch=shared->load_epoch;shared->source_club=1043;
    shared->team=team;shared->league=league;shared->status=0;shared->sequence=seq;
    shared->reserved=GetTickCount();
    menu_data[0x10]=0;
}
int main(void)
{
    JobsShared channel={0};int i;
    shared=&channel;shared->ready=1;shared->load_epoch=1;
    mocked_profile.registry=0x12345678;mocked_profile.context=0x998877;
    mocked_profile.club=1043;mocked_profile.manager=manager_data;mocked_profile.standings=manager_data;
    mocked_profile.menu=menu_data;
    *(uintptr_t *)menu_data=0x0304bfe8;
    *(uintptr_t *)(menu_data+8)=mocked_profile.registry;
    *(uintptr_t *)(menu_data+0x1348)=mocked_profile.registry;
    menu_data[0x20]=1;menu_event=fake_menu;
    *(uintptr_t *)(manager_data+0xd8)=(uintptr_t)native_rows;
    *(uintptr_t *)(manager_data+0xe0)=(uintptr_t)(native_rows+2);
    *(uintptr_t *)(manager_data+0xe8)=(uintptr_t)(native_rows+64);
    native_rows[0][0]=383;native_rows[0][1]=7;native_rows[1][0]=598;native_rows[1][1]=7;
    gather=fake_gather;add_offer=fake_add;inform=fake_inform;withdraw_offer=fake_withdraw;
    *(int *)(manager_data+0x14)=3;clear_offer();reenter=1;
    request(1,130285,350);mocked_hub=0;process_current();
    assert(mails==0 && contracts==0 && shared->completed==0);
    mocked_hub=1;menu_data[0x10]=1;process_current();
    assert(mails==1 && contracts==0 && shared->status==0 && shared->completed==1);
    for(i=0;i<20;++i)process_current();assert(mails==1 && contracts==0);
    menu_data[0x10]=0;process_current();
    assert(shared->completed==1 && shared->status==1 && shared->count==1 && mails==1);
    assert(contracts==1 && !pending_contract_seq);
    assert(active_offer()[0]==130285 && active_offer()[6]==date);
    assert(shared->reserved==3);
    for(i=0;i<100;++i)process_current();assert(mails==1 && contracts==1);
    request(2,112119,83);process_current();
    assert(shared->status==1 && active_offer()[0]==112119 && mails==2);
    assert(withdrawals==1 && last_archived==130285);
    ++date;request(3,112119,83);process_current();
    assert(shared->status==1 && active_offer()[6]==date && mails==3);
    assert(withdrawals==2 && last_archived==112119);
    /* Native refusal/expiration/signature removes the offer. Neither ticks nor
     * a native vacancy regeneration may recreate it or resend its email. */
    clear_offer();*(uintptr_t *)(manager_data+0xe0)=(uintptr_t)(native_rows+2);
    for(i=0;i<10;++i) {++date;process_current();}
    assert(active_offer()[0]==-1 && !find_offer(manager_data,130285,350) && mails==3);
    request(4,130285,350);process_current();assert(mails==4 && shared->status==1);
    clear_offer();active_offer()[8]=383;active_offer()[9]=20000;active_offer()[10]=3;
    request(5,112119,83);process_current();assert(shared->status==1 && mails==5);
    assert(active_offer()[0]==112119 && active_offer()[8]==-1 && active_offer()[10]==-1);
    request(6,9999,7);process_current();
    assert(shared->error==2 && active_offer()[0]==112119 && mails==5 && withdrawals==2);
    request(7,999,7);shared->registry++;process_current();
    assert(shared->status==-1 && shared->error==1 && !find_offer(manager_data,999,7));
    request(8,1043,7);process_current();assert(shared->status==-1 && mails==5);
    shared->load_epoch++;process_current();assert(shared->count==0);
    request(9,112119,83);shared->request_epoch--;process_current();assert(shared->status==-1);
    request(10,130285,350);shared->reserved=GetTickCount()-90001U;process_current();
    assert(shared->error==8 && !pending_contract_seq);
    request(11,130285,350);menu_data[0x10]=1;process_current();
    assert(pending_contract_seq==11 && shared->status==0);
    shared->load_epoch++;process_current();
    assert(!pending_contract_seq && shared->status==-1 && shared->error==1);
    request(12,130285,350);inform=failed_inform;process_current();
    assert(shared->status==-1 && shared->error==6 && !shared->ready);
    puts("PASS: FIFA EnterJobOfferSign queued once after proposal; busy UI defers confirmation without duplicate mail; outside hub never delivers; changed career cancels deferred UI; no forced acceptance; replacement, invalid destination, expiry and reentrancy guards preserved");
    return 0;
}
