#ifndef MANAGER_PROFILE_WIRE_H
#define MANAGER_PROFILE_WIRE_H
#include <string.h>
#include <stdlib.h>
static int manager_profile_wire_valid(const char *wire)
{
    char copy[512],*token,*end;unsigned i;long value;
    size_t length=strlen(wire);
    if(length>=sizeof(copy)||strncmp(wire,"S16MGRP1|",9)
        ||strspn(wire,"S16MGRPENDabcdef0123456789|-_")!=length)return 0;
    memcpy(copy,wire,length+1);token=copy+9;end=strchr(token,'|');
    if(!end||end-token!=64||strspn(token,"0123456789abcdef")!=64)return 0;
    token=end+1;
    for(i=0;i<12;++i){
        value=strtol(token,&end,10);
        if(end==token||*end!='|'||value<(i?0:-1)||value>200000)return 0;
        if(i==1&&value>4)return 0;
        token=end+1;
    }
    return !strcmp(token,"END");
}
#endif
