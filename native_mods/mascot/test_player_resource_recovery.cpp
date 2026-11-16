#define PLAYER_RESOURCE_POLICY_ONLY
#include "player_resource_recovery.h"
#include <cassert>
int main(){
    PlayerResourceRetry r;
    assert(!r.observe(1000,1,2,3,189362,true));
    assert(!r.observe(2499,1,2,3,189362,true));
    assert(r.observe(2500,1,2,3,189362,true));
    assert(!r.observe(7000,1,2,3,189362,true));
    assert(r.observe(7500,1,2,3,189362,true));
    assert(!r.observe(13000,1,2,3,189362,true));
    assert(!r.observe(14000,1,2,3,50182,true));
    assert(r.observe(15500,1,2,3,50182,true));
    assert(!r.observe(16000,1,2,3,50182,false));
    PlayerResourceRetry loading;
    assert(!loading.observe(1000,8,9,10,1,true));
    assert(!loading.observe(1500,8,9,10,1,false));
    assert(!loading.observe(2500,8,9,10,1,true));
    assert(!loading.observe(3500,8,9,10,1,false));
}
