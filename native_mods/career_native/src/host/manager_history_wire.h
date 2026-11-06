#ifndef MANAGER_HISTORY_WIRE_H
#define MANAGER_HISTORY_WIRE_H
#include <string.h>
#include <stdlib.h>
static int manager_history_wire_valid(const char *wire)
{
    const char *p;char *end;unsigned i;long value;
    if(!wire||strlen(wire)>256||strncmp(wire,"S16MGRH1|",9))return 0;
    p=wire+9;
    if(strspn(p,"0123456789abcdef")!=64||p[64]!='|')return 0;
    p+=65;
    for(i=0;i<5;++i){value=strtol(p,&end,10);if(end==p||*end!='|'||value<0||value>200000)return 0;p=end+1;}
    return !strcmp(p,"END");
}
#endif
