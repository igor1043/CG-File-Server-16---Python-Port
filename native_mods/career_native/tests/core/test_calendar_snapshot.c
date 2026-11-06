#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../src/core/fce_runtime.h"
struct FceLiveSnapshot {volatile LONG refs;unsigned long generation;FceModel model;};
static SRWLOCK snapshot_lock=SRWLOCK_INIT;
static FceLiveSnapshot *calendar_current;
static volatile LONG generation=1,publication_revision;
static DWORD engine_thread;
static unsigned char *module;
static unsigned fixture_copies,fixture_models,fixture_releases;
static int fixture_date=20260101,fixture_change_date;
static int fixture_read_date(void){return fixture_date;}
static FceRuntimeDateCallback date_callback=fixture_read_date;
int fce_date_valid(int date){return date>=20260101 && date<=20261231;}
FceResult fce_model_build(const FceRawTable *tables,int date,FceModel *model){
    assert(tables[0].count==1 && tables[1].count==1 && tables[2].count==0 && tables[2].stride==0x25 && tables[3].count==1);
    memset(model,0,sizeof(*model));model->date=date;++fixture_models;return FCE_OK;
}
void fce_runtime_release(FceLiveSnapshot *snapshot){if(snapshot && InterlockedDecrement(&snapshot->refs)==0){++fixture_releases;free(snapshot);}}
static int copy_table(void *manager,size_t offset,FceRawTable *table){
    assert(manager==(void *)123 && (offset==0x48 || offset==0x80 || offset==0x58));
    ++fixture_copies;table->count=1;table->stride=0x40;table->bytes=calloc(1,0x40);
    if(fixture_change_date && offset==0x58)++fixture_date;return 1;
}
#include "../../src/core/calendar_snapshot.inc"
int main(void){
    unsigned char iface[64]={0},hub[64]={0},connector[64]={0};unsigned i;FceLiveSnapshot *previous;
    module=calloc(1,0xa0000);assert(module);engine_thread=GetCurrentThreadId();
    *(void ***)iface=(void **)(module+0x94360);iface[0x30]=1;
    *(void **)(iface+0x18)=hub;*(void **)(hub+0x28)=connector;*(void **)(connector+0x18)=(void *)123;
    /* Consecutive dates never need two visual captures with an identical day. */
    for(i=0;i<90;++i){fixture_date=20260101+(int)(i/28)*100+(int)(i%28);calendar_capture(iface);assert(calendar_current && calendar_current->model.date==fixture_date);}
    assert(fixture_models==90 && fixture_copies==270 && fixture_releases==89);
    calendar_capture(iface);assert(fixture_models==90); /* Same-day bounded poll. */
    ++fixture_date;fixture_change_date=1;previous=calendar_current;calendar_capture(iface);assert(calendar_current==previous && fixture_models==90);fixture_change_date=0;
    calendar_capture(iface);assert(calendar_current->model.date==fixture_date && fixture_models==91);
    ++engine_thread;++fixture_date;calendar_capture(iface);assert(fixture_models==91);--engine_thread;
    ++generation;previous=calendar_current;calendar_current=NULL;fce_runtime_release(previous);calendar_capture(iface);assert(calendar_current && fixture_models==92);
    iface[0x30]=0;++fixture_date;previous=calendar_current;calendar_capture(iface);assert(calendar_current==previous);
    fce_runtime_release(calendar_current);free(module);
    puts("PASS: calendar snapshots advance without UI settling; date/epoch/owner checks and bounded polling preserved");return 0;
}
