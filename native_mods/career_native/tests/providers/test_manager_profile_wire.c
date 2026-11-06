#include <assert.h>
#include <stdio.h>
#include "../../src/host/manager_profile_wire.h"
int main(void){
 const char *token="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
 char wire[512];
 snprintf(wire,sizeof(wire),"S16MGRP1|%s|5|0|1|2|100|1|1|11|0|0|0|40|END",token);assert(manager_profile_wire_valid(wire));
 snprintf(wire,sizeof(wire),"S16MGRP1|%s|-1|0|1|2|100|1|1|11|0|0|0|40|END",token);assert(manager_profile_wire_valid(wire));
 snprintf(wire,sizeof(wire),"S16MGRP1|%s|5|5|1|2|100|1|1|11|0|0|0|40|END",token);assert(!manager_profile_wire_valid(wire));
 snprintf(wire,sizeof(wire),"S16MGRP1|%s|-2|0|1|2|100|1|1|11|0|0|0|40|END",token);assert(!manager_profile_wire_valid(wire));
 assert(!manager_profile_wire_valid("S16MGRP1|bad|1|END"));assert(!manager_profile_wire_valid("S16MGRP1|../escape"));
 snprintf(wire,sizeof(wire),"S16MGRP1|%s|5|4|1|2|100|1|1|11|0|0|0|540|END",token);assert(manager_profile_wire_valid(wire));
 puts("PASS: explicit manager profile/cancel wire, bounded navigation, malformed requests rejected");return 0;
}
