#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../src/host/career_retirement_live.h"
typedef struct Fixture {RetirementLiveRow rows[4];int valid,writes,fail_write,partial_fail;} Fixture;
static int scope(void *p){return ((Fixture *)p)->valid;}
static int read_row(void *p,int id,RetirementLiveRow *out){Fixture *f=p;int i;for(i=0;i<4;++i)if(f->rows[i].id==id){*out=f->rows[i];return 1;}return 0;}
static int write_row(void *p,const RetirementLiveRow *old,const RetirementLiveRow *next){
    Fixture *f=p;int i;++f->writes;
    for(i=0;i<4;++i)if(f->rows[i].id==old->id && retirement_live_equal(f->rows+i,old)){
        if(f->writes==f->fail_write){if(f->partial_fail)f->rows[i]=*next;return 0;}
        f->rows[i]=*next;return 1;
    }return 0;
}
static int rating(void *unused,int *out){(void)unused;*out=63;return 1;}
static Fixture fixture(void){
    Fixture f={0};int i,j;f.valid=1;
    for(i=0;i<4;++i){f.rows[i].id=i+1;f.rows[i].retiring=i<2;f.rows[i].birthdate=145000+i*1000;
        f.rows[i].overall=86-i*4;f.rows[i].potential=90+i;
        for(j=0;j<RETIREMENT_LIVE_ATTRIBUTES;++j)f.rows[i].attributes[j]=35+(j*7+i)%60;}
    return f;
}
int main(void){
    Fixture f=fixture();RetirementLiveOps ops={&f,scope,read_row,write_row,rating};RetirementLiveRow selected[2],original;RetirementLiveResult r;int after,i,j;
    selected[0]=f.rows[0];selected[1]=f.rows[1];
    r=retirement_live_apply(ops,selected,2,0,20261107,18);
    assert(r.status==0 && r.changed==2 && f.rows[0].retiring==0 && f.rows[0].birthdate==145000 && f.rows[2].retiring==0 && f.rows[2].birthdate==147000);
    assert(f.rows[0].overall==86 && f.rows[0].potential==90 && f.rows[0].attributes[0]==35);
    /* A new snapshot after a repeated click finds no eligible players. */
    r=retirement_live_apply(ops,NULL,0,0,20261107,18);assert(r.status==0 && !r.changed && f.writes==2);
    f=fixture();f.valid=0;selected[0]=f.rows[0];r=retirement_live_apply(ops,selected,1,0,20261107,18);assert(r.status==1 && !f.writes);
    f=fixture();selected[0]=f.rows[0];selected[1]=f.rows[0];r=retirement_live_apply(ops,selected,2,0,20261107,18);assert(r.status==1 && !f.writes);
    f=fixture();selected[0]=f.rows[0];selected[0].birthdate++;r=retirement_live_apply(ops,selected,1,0,20261107,18);assert(r.status==1 && !f.writes);
    f=fixture();selected[0]=f.rows[0];selected[1]=f.rows[1];f.fail_write=2;
    r=retirement_live_apply(ops,selected,2,0,20261107,18);assert(r.status==2 && r.restored==2 && !r.changed && f.rows[0].retiring==1 && f.rows[1].retiring==1);
    f=fixture();selected[0]=f.rows[0];selected[1]=f.rows[1];f.fail_write=2;f.partial_fail=1;
    r=retirement_live_apply(ops,selected,2,1,20261107,18);assert(r.status==2 && r.restored==2 && f.rows[0].birthdate==145000 && f.rows[1].birthdate==146000);
    f=fixture();selected[0]=f.rows[0];r=retirement_live_apply(ops,selected,1,1,20260230,18);assert(r.status==1 && !f.writes);
    /* Parity with the existing Python save worker, including leap birthday. */
    assert(retirement_live_birthdate(145438,20261019,18,&after) && after==155299);
    assert(retirement_live_birthdate(145082,20261019,18,&after) && after==155309);
    assert(retirement_live_birthdate(145139,20240228,18,&after) && after==154270);
    assert(!retirement_live_birthdate(-1,20261107,18,&after));
    /* Every allowed draw produces the requested OVR and keeps potential.
     * Technical/physical/GK ratings share the same proportional scaling. */
    for(i=60;i<=65;++i){
        f=fixture();original=f.rows[0];assert(retirement_live_youth_ratings(f.rows,i));
        assert(f.rows[0].overall==i && f.rows[0].potential==original.potential);
        for(j=0;j<RETIREMENT_LIVE_ATTRIBUTES;++j)
            assert(f.rows[0].attributes[j]==(original.attributes[j]*i+43)/86);
    }
    f=fixture();selected[0]=f.rows[0];original=f.rows[2];
    r=retirement_live_apply(ops,selected,1,1,20261107,18);
    assert(r.status==0 && f.rows[0].overall==63 && f.rows[0].potential==90 && f.rows[0].retiring==0
        && f.rows[0].birthdate!=145000 && retirement_live_equal(f.rows+2,&original));
    f=fixture();selected[0]=f.rows[0];selected[1]=f.rows[1];original=f.rows[0];f.fail_write=2;f.partial_fail=1;
    r=retirement_live_apply(ops,selected,2,1,20261107,18);
    assert(r.status==2 && retirement_live_equal(f.rows,&original) && f.rows[1].overall==82);
    f=fixture();f.rows[0].attributes[6]=100;selected[0]=f.rows[0];
    r=retirement_live_apply(ops,selected,1,1,20261107,18);assert(r.status==1 && !f.writes);
    f=fixture();original=f.rows[0];assert(!retirement_live_youth_ratings(f.rows,66));assert(retirement_live_equal(f.rows,&original));
    puts("Live retirement: scoped updates, age parity, 60..65 OVR, 33 proportional attributes, unchanged potential/simple removal, full rollback passed.");return 0;
}
