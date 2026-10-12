#define WIN32_LEAN_AND_MEAN
#include "../native_mods/match_presentation.h"
#include <cassert>
int main() {
    MatchPresentationOptions options;
    assert(options.mascots);
    assert(!options.entrance_allowed() && !options.goal_allowed());
    options.entrance=true;
    assert(!options.entrance_allowed());
    options.pyrotechnics=true;
    assert(options.entrance_allowed() && !options.goal_allowed());
    options.goal=true;
    assert(options.goal_allowed());
    options.pyrotechnics=false;
    assert(!options.entrance_allowed() && !options.goal_allowed());
    return 0;
}
