#include "presentation.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
int main() {
    const char* menus[]={"game/screens/playNow/SelectTeam","game/screens/playNow/SideSelect",
        "game/screens/playNow/KickOffHub","game/screens/playNow/KitSelect",
        "game/screens/misc/ArenaPlayer","game/screens/training/SkillGame",
        "game/screens/postGameFlow/MatchResults","game/screens/career/Hub"};
    // Stale club metadata AND two retained native teams must not unlock a menu.
    bool openingConsumed=false;
    for(const char* menu:menus) {
        const auto page=pyro_page(menu,true);
        assert(page==PyroPage::Outside);
        assert(!pyro_can_start(page,true));
        assert(!pyro_can_continue(page,true,true));
        if(pyro_can_start(page,true))openingConsumed=true;
    }
    assert(!openingConsumed);
    assert(!pyro_can_start(pyro_page("",false),true));
    assert(!pyro_can_start(pyro_page("",true),false));
    assert(pyro_can_start(pyro_page(" \t",true),true));
    assert(pyro_can_start(pyro_page("game/screens/TV/bumper",true),true));
    for(const char* pause:{"game/screens/misc/StadiumPan","game/screens/fluxHub/FluxHub",
                          "game/screens/instantReplay/ReplayScreen"}) {
        const auto page=pyro_page(pause,true);
        assert(!pyro_can_start(page,true));
        assert(!pyro_can_continue(page,true,false));
        assert(pyro_can_continue(page,true,true));
    }
    std::puts("Preview never consumes opening; native teams required; presentation allowed before kickoff; pause/replay cannot arm: PASS");
}
