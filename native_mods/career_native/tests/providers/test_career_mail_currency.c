#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
static unsigned char *g_module_base;
static int is_readable_range(const void*p,size_t n){MEMORY_BASIC_INFORMATION m;return p && VirtualQuery(p,&m,sizeof(m)) && m.State==MEM_COMMIT && !(m.Protect&(PAGE_GUARD|PAGE_NOACCESS)) && (uintptr_t)p+n<=(uintptr_t)m.BaseAddress+m.RegionSize;}
static int read_card_scope(uintptr_t at,void*out,size_t n){if(!is_readable_range((void*)at,n))return 0;memcpy(out,(void*)at,n);return 1;}
#include "../../src/host/career_mail_currency.inc"
static int formatted,released;static DWORD owner;
static void format(void*self,CareerMoneyString*text,unsigned char compact,int amount,int slot){
 char buffer[128];(void)self;assert(GetCurrentThreadId()==owner && !compact);++formatted;
 sprintf(buffer,"native-slot%d:%d",slot,amount);text->begin=_strdup(buffer);text->end=text->begin+strlen(buffer);text->capacity=text->end+1;
}
static void release(void*p){++released;free(p);}
static void jump(unsigned rva,uintptr_t function,int prefix){
 unsigned char bytes[19]={0x48,0x89,0x5c,0x24,0x08,0xff,0x25,0,0,0,0};
 if(prefix){memcpy(bytes+11,&function,8);memcpy(g_module_base+rva,bytes,19);}
 else{memcpy(bytes,"\xff\x25\0\0\0\0",6);memcpy(bytes+6,&function,8);memcpy(g_module_base+rva,bytes,14);}
}
int main(void){
 char output[512],small[8];uintptr_t localizer;owner=GetCurrentThreadId();
 g_module_base=VirtualAlloc(NULL,0x5000000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);assert(g_module_base);
 localizer=(uintptr_t)g_module_base+0x1000;*(uintptr_t*)localizer=(uintptr_t)g_module_base+0x21993f0;
 *(uintptr_t*)(g_module_base+0x351a0b0)=localizer;*(uintptr_t*)(g_module_base+0x21993f0+0x68)=(uintptr_t)g_module_base+0x3d33bc0;
 jump(0x3d33bc0,(uintptr_t)format,1);jump(0x489b140,(uintptr_t)release,0);
 FlushInstructionCache(GetCurrentProcess(),g_module_base,0x5000000);
 career_mail_currency("Before {{S16M:0:16000000}} / after {{S16M:2:17000000}}.",output,sizeof(output));
 assert(!strcmp(output,"Before native-slot0:16000000 / after native-slot2:17000000."));assert(formatted==2 && released==2);
 career_mail_currency("{{S16M:1:0}}",output,sizeof(output));assert(!strcmp(output,"native-slot1:0"));
 career_mail_currency("{{S16M:3:1}}",output,sizeof(output));assert(!strcmp(output,"{{S16M:3:1}}"));
 career_mail_currency("{{S16M:2:99999999999999}}",output,sizeof(output));assert(strstr(output,"99999999999999"));
 career_mail_currency("123456789",small,sizeof(small));assert(!strcmp(small,"1234567"));
 *(uintptr_t*)localizer=0;career_mail_currency("{{S16M:2:123}}",output,sizeof(output));assert(!strcmp(output,"123"));
 assert(formatted==released);VirtualFree(g_module_base,0,MEM_RELEASE);
 puts("PASS native career currency: correct ABI, save slot, all amounts, bounded mail, allocation release, safe fallback");return 0;
}
