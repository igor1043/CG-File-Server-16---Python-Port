#ifndef MANAGER_SETTINGS_WIRE_H
#define MANAGER_SETTINGS_WIRE_H
#include <string.h>
static int manager_settings_wire_valid(const char *wire)
{
    const char *p; size_t length;
    if(!wire)return 0;
    length=strlen(wire);
    if(length>128||strncmp(wire,"S16MGRS1|",9))return 0;
    p=wire+9;
    if(strspn(p,"0123456789abcdef")!=64||p[64]!='|')return 0;
    p+=65;
    if((p[0]!='0'&&p[0]!='1')||p[1]!='|'||p[2]<'0'||p[2]>'2'||p[3]!='|')return 0;
    p+=4;length=strspn(p,"0123456789");
    return length>0&&length<=9&&!strcmp(p+length,"|END");
}
#endif
