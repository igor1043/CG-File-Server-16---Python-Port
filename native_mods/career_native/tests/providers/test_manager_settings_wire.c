#include <assert.h>
#include <stdio.h>
#include "../../src/host/manager_settings_wire.h"
int main(void)
{
    char wire[256];
    const char *hash="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    unsigned e,c;
    for(e=0;e<2;++e)for(c=0;c<3;++c){snprintf(wire,sizeof(wire),"S16MGRS1|%s|%u|%u|42|END",hash,e,c);assert(manager_settings_wire_valid(wire));}
    snprintf(wire,sizeof(wire),"S16MGRS1|%s|2|0|1|END",hash);assert(!manager_settings_wire_valid(wire));
    snprintf(wire,sizeof(wire),"S16MGRS1|%s|1|3|1|END",hash);assert(!manager_settings_wire_valid(wire));
    snprintf(wire,sizeof(wire),"S16MGRS1|%s|1|1|1|END|extra",hash);assert(!manager_settings_wire_valid(wire));
    assert(!manager_settings_wire_valid("S16MGRS1|a|1|1|1|END"));assert(!manager_settings_wire_valid(""));assert(!manager_settings_wire_valid(NULL));
    puts("manager_settings_wire: ok");return 0;
}
