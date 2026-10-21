#pragma once

// Verified FIFA16 577de45c enum: the switch at 3a30370 maps value 11 to
// GAME_STATE_IS_GAMESTATE_SHOOTOUT; 7 is an ordinary in-match penalty.
// The flow name getter at 3d89f00 maps substate 13 to PENALTY_SHOOTOUT.
struct PyroShootout {
    bool active=false;
    bool sample(bool selector,int sports,int flowSubstate,bool outside,bool freshKickoff=false) {
        if(outside || freshKickoff)active=false;
        else if(selector || sports==11 || flowSubstate==13)active=true;
        // Out-of-play, replay, pause, and missing samples cannot release it.
        return active;
    }
};
