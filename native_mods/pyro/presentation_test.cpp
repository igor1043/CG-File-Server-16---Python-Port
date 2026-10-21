#include "presentation.h"
#include "goals.h"
#include "shootout.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
#define WIN32_LEAN_AND_MEAN
#include "match_presentation.h"
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
    assert(pyro_page("game/screens/postGameFlow/PenaltyKickSelect",true,true)==PyroPage::Pause);
    assert(pyro_shootout_page("GAME/SCREENS/POSTGAMEFLOW/PENALTYKICKSELECT"));
    PyroShootout shootout;
    assert(!shootout.sample(false,7,14,false)); // A regulation penalty remains eligible.
    assert(shootout.sample(false,11,14,false)); // Native shootout, no selector (player career).
    for(int sports:{14,15,-1,7})assert(shootout.sample(false,sports,14,false));
    assert(!shootout.sample(false,14,14,true)); // Genuine results/menu.
    assert(shootout.sample(true,14,14,false)); // Exact observed selector page.
    assert(shootout.sample(false,14,14,false));
    assert(!shootout.sample(false,2,14,false,true)); // A real fresh kickoff.
    assert(shootout.sample(false,1,13,false)); // Native pre-shootout overlay before the selector.
    MatchPresentationOptions switches;
    switches.pyrotechnics=true;switches.entrance=true;switches.goal=true;
    assert(switches.entrance_allowed() && switches.goal_allowed());
    for(const char* menu:menus) {
        assert(!(switches.entrance_allowed() && pyro_can_start(pyro_page(menu,true),true)));
        assert(!(switches.goal_allowed() && pyro_can_start(pyro_page(menu,true),true)));
    }
    switches.entrance=false;
    assert(!switches.entrance_allowed() && switches.goal_allowed());
    switches.pyrotechnics=false;
    assert(!switches.entrance_allowed() && !switches.goal_allowed());
    assert(!pyro_can_start(pyro_page("",false),true));
    assert(!pyro_can_start(pyro_page("",true),false));
    assert(pyro_can_start(pyro_page(" \t",true),true));
    assert(pyro_can_start(pyro_page("game/screens/TV/bumper",true),true));
    assert(pyro_can_start(pyro_page("TV/bumper",true),true));
    assert(pyro_can_start(pyro_page("game/screens/misc/StadiumPan",true),true));
    assert(!pyro_can_start(pyro_page("game/screens/misc/StadiumPan",true),false));
    for(const char* pause:{"game/screens/fluxHub/FluxHub",
                          "game/screens/instantReplay/ReplayScreen","game/screens/pause/PauseMenu"}) {
        const auto page=pyro_page(pause,true);
        assert(!pyro_can_start(page,true));
        assert(!pyro_can_continue(page,true,false));
        assert(pyro_can_continue(page,true,true));
    }
    PyroMatchSession session;
    assert(session.observe(100,1043,1041));
    for(const char* overlay:{"game/screens/playNow/SideSelect","game/screens/matchDetails/MatchDetails"}) {
        assert(pyro_page(overlay,true)==PyroPage::Outside);
        const auto paused=pyro_page(overlay,true,session.key!=0);
        assert(paused==PyroPage::Pause);
        assert(!pyro_can_start(paused,true));
        assert(pyro_can_continue(paused,true,true));
        // Resume with recreated Lua tables at 0:0 cannot arm another opening.
        assert(!session.observe(200,1043,1041));
        assert(session.key==100);
        assert(pyro_can_start(pyro_page("",true,true),true));
    }
    assert(!session.observe(300,1043,1041)); // replay/resource rebuild
    session=PyroMatchSession{}; // confirmed restart or leave match
    assert(session.observe(400,1043,1041));
    assert(session.observe(500,383,1041)); // different fixture
    PyroGoals score;
    assert(!score.update(100,0,0));
    assert(!score.update(200,1,0));
    assert(score.update(300,1,0));
    // Pause and scene reconstruction do not clear the score baseline.
    assert(!score.update(10000,1,0));
    assert(!score.update(10100,1,0));
    assert(!score.update(10200,1,1));
    assert(!score.update(10300,1,1)); // away goal does not trigger
    assert(!score.update(10400,2,1));
    assert(score.update(10500,2,1)); // next home goal still triggers
    std::puts("Pause side selection/details and rebuilt scene tables preserve match session; restart/new fixture rearm: PASS");
    std::puts("Preview never consumes opening; native teams required; presentation allowed before kickoff; pause/replay cannot arm: PASS");
}
