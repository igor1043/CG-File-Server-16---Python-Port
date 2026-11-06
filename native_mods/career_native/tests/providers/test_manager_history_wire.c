#include <assert.h>
#include <stdio.h>
#include "../../src/host/manager_history_wire.h"
int main(void)
{
    const char *token="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";char wire[256];
    snprintf(wire,sizeof(wire),"S16MGRH1|%s|1043|1|7|0|40|END",token);assert(manager_history_wire_valid(wire));
    snprintf(wire,sizeof(wire),"S16MGRH1|%s|-1|1|7|0|40|END",token);assert(!manager_history_wire_valid(wire));
    snprintf(wire,sizeof(wire),"S16MGRH1|%s|1043|1|7|0|40|END|extra",token);assert(!manager_history_wire_valid(wire));
    snprintf(wire,sizeof(wire),"S16MGRH1|%s|1043|1|7|0|200001|END",token);assert(!manager_history_wire_valid(wire));
    assert(!manager_history_wire_valid("S16MGRH1|bad|1043|1|7|0|40|END"));assert(!manager_history_wire_valid(NULL));
    puts("manager_history_wire: ok");return 0;
}
