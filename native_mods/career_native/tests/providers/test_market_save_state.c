#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../../src/host/career_market_save_state.h"
static void fixture(const char *tail){
 FILE *file=fopen("market-state-fixture.tsv","wb");assert(file);
 fputs("schema=1\npid=10\ncreated=20\ncontext=30\nepoch=2\ndate=20261231\nclub=598\n",file);fputs(tail,file);fclose(file);
}
int main(void){
 CareerMarketSaveState state;
 const char *path="market-state-fixture.tsv";
 fixture("revision=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n");
 assert(career_market_save_state_read(path,10,20,2,&state));assert(state.context==0x30&&state.date==20261231&&state.club==598);
 assert(!career_market_save_state_read(path,11,20,2,&state));assert(!career_market_save_state_read(path,10,21,2,&state));assert(!career_market_save_state_read(path,10,20,3,&state));
 fixture("revision=invalid\n");assert(!career_market_save_state_read(path,10,20,2,&state));
 remove(path);assert(!career_market_save_state_read(path,10,20,2,&state));
 puts("PASS: exact committed market revision; process/load isolation; malformed and missing handoffs rejected");return 0;
}
