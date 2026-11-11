#pragma once
#include <stdint.h>

// Config values: both = 0, home = 1, away = 2.
inline bool scene_team_allowed(int setting,int side) {
    return side>=0 && side<2 && (setting==0 || setting==side+1);
}
