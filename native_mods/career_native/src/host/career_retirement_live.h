#ifndef CAREER_RETIREMENT_LIVE_H
#define CAREER_RETIREMENT_LIVE_H
#include <stdlib.h>

/* The host owns the engine thread, selection and database. No pointers to
 * FIFA objects are retained by this transaction across UI ticks or saves. */
#define RETIREMENT_LIVE_ATTRIBUTES 33
typedef struct RetirementLiveRow {
    int id, retiring, birthdate, overall, potential;
    int attributes[RETIREMENT_LIVE_ATTRIBUTES];
} RetirementLiveRow;
typedef struct RetirementLiveOps {
    void *user;
    int (*scope)(void *);
    int (*read)(void *,int,RetirementLiveRow *);
    int (*write)(void *,const RetirementLiveRow *,const RetirementLiveRow *);
    int (*rating)(void *,int *);
} RetirementLiveOps;
typedef struct RetirementLiveResult { int status, eligible, changed, restored; } RetirementLiveResult;

static int retirement_live_leap(int y) { return y%4==0 && (y%100!=0 || y%400==0); }
static int retirement_live_month(int y,int m) {
    static const int days[]={31,28,31,30,31,30,31,31,30,31,30,31};
    return m>=1 && m<=12?days[m-1]+(m==2 && retirement_live_leap(y)):0;
}
static int retirement_live_birthdate(int before,int today,int age,int *after) {
    int y=1582,m=1,d,by,bm,bd,ty=today/10000,tm=today/100%100,td=today%100,n,i;
    /* Days since 1582-10-14, as used by the existing save worker. */
    if(before<0 || before>300000 || age<12 || age>50 || ty<1900 || ty>2400
        || tm<1 || tm>12 || td<1 || td>retirement_live_month(ty,tm))return 0;
    n=before+286; /* 1582-10-14 is day 287 of the proleptic year. */
    while(n>=365+retirement_live_leap(y)){n-=365+retirement_live_leap(y);++y;}
    while(n>=retirement_live_month(y,m)){n-=retirement_live_month(y,m);++m;}
    d=n+1;by=ty-age-((tm<m)||(tm==m && td<d));bm=m;
    bd=d>retirement_live_month(by,bm)?retirement_live_month(by,bm):d;
    if(by<1582 || by>2400)return 0;
    n=-286;for(i=1582;i<by;++i)n+=365+retirement_live_leap(i);
    for(i=1;i<bm;++i)n+=retirement_live_month(by,i);
    *after=n+bd-1;return 1;
}
static int retirement_live_compare(const void *a,const void *b) {
    const RetirementLiveRow *x=(const RetirementLiveRow *)a,*y=(const RetirementLiveRow *)b;
    return (x->id>y->id)-(x->id<y->id);
}
static int retirement_live_equal(const RetirementLiveRow *a,const RetirementLiveRow *b) {
    int i;
    if(a->id!=b->id || a->retiring!=b->retiring || a->birthdate!=b->birthdate
        || a->overall!=b->overall || a->potential!=b->potential)return 0;
    for(i=0;i<RETIREMENT_LIVE_ATTRIBUTES;++i)if(a->attributes[i]!=b->attributes[i])return 0;
    return 1;
}
static int retirement_live_youth_ratings(RetirementLiveRow *row,int target) {
    int i,value;
    if(target<60 || target>65 || row->overall<1 || row->overall>99
        || row->potential<1 || row->potential>99)return 0;
    for(i=0;i<RETIREMENT_LIVE_ATTRIBUTES;++i){
        if(row->attributes[i]<1 || row->attributes[i]>99)return 0;
        value=(row->attributes[i]*target+row->overall/2)/row->overall;
        row->attributes[i]=value<1?1:value>99?99:value;
    }
    row->overall=target;return 1;
}
/* 0 success, 1 rejected before writing, 2 failed and fully restored,
 * 3 failed restoration (must not be presented as success or auto-retried). */
static RetirementLiveResult retirement_live_apply(RetirementLiveOps ops,
    RetirementLiveRow *before,int count,int rejuvenate,int today,int age)
{
    RetirementLiveResult result={1,count,0,0};RetirementLiveRow now,*after;
    int i,target,touched=0,ok=1;
    if(count<0 || count>50000 || (count && !before) || !ops.scope || !ops.read || !ops.write
        || !ops.scope(ops.user) || (rejuvenate!=0 && rejuvenate!=1) || (rejuvenate && !ops.rating))return result;
    if(!count){result.status=0;return result;}
    after=(RetirementLiveRow *)malloc((size_t)count*sizeof(*after));if(!after)return result;
    qsort(before,(size_t)count,sizeof(*before),retirement_live_compare);
    for(i=0;i<count;++i){
        if(before[i].id<=0 || before[i].retiring!=1 || (i && before[i-1].id==before[i].id)
            || !ops.read(ops.user,before[i].id,&now) || !retirement_live_equal(&now,before+i))goto done;
        after[i]=before[i];after[i].retiring=0;
        if(rejuvenate && (!retirement_live_birthdate(before[i].birthdate,today,age,&after[i].birthdate)
            || !ops.rating(ops.user,&target) || !retirement_live_youth_ratings(after+i,target)))goto done;
    }
    if(!ops.scope(ops.user))goto done;
    for(i=0;i<count;++i){
        if(!ops.scope(ops.user)){ok=0;break;}
        touched=i+1;
        if(!ops.write(ops.user,before+i,after+i) || !ops.read(ops.user,before[i].id,&now)
            || !retirement_live_equal(&now,after+i)){ok=0;break;}
    }
    if(ok && ops.scope(ops.user)){
        for(i=0;i<count;++i)if(!ops.read(ops.user,before[i].id,&now)
            || !retirement_live_equal(&now,after+i)){ok=0;break;}
    }else ok=0;
    if(ok){result.status=0;result.changed=count;goto done;}
    result.status=2;
    for(i=touched-1;i>=0;--i){
        if(!ops.scope(ops.user) || !ops.read(ops.user,before[i].id,&now) || now.id!=before[i].id) {result.status=3;continue;}
        if(!retirement_live_equal(&now,before+i) && !ops.write(ops.user,&now,before+i)){result.status=3;continue;}
        if(!ops.read(ops.user,before[i].id,&now) || !retirement_live_equal(&now,before+i))result.status=3;
        else ++result.restored;
    }
done:
    free(after);return result;
}
#endif
