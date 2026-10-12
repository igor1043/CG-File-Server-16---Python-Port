#pragma once

struct MascotReplayClockSample { uintptr_t source=0; double time=0; bool replay=false,valid=false; };
static MascotReplayClockSample mascot_read_replay_clock() {
    MascotReplayClockSample result;
    uintptr_t object,vt,getTime,getReplay,again;
    double time,timeAgain;unsigned char replay,replayAgain;
    // GameStateInterface::GetTime and IsReplayActive, identified from the
    // native replay writer and GAME_STATE_IS_REPLAY_ACTIVE consumer.
    if(!get(image+0x3517c10,object) || !get(object,vt) || vt!=image+0x20ff390 ||
       !get(vt+0x30,getTime) || getTime!=image+0x39fee10 ||
       !get(vt+0x70,getReplay) || getReplay!=image+0x3a00d60 ||
       !get(object+0x20,time) || !get(object+0x39,replay) || replay>1 ||
       !get(object+0x20,timeAgain) || !get(object+0x39,replayAgain) ||
       time!=timeAgain || replay!=replayAgain || !isfinite(time) || time<0 || time>1e9 ||
       !get(image+0x3517c10,again) || object!=again)return result;
    result.source=object;result.time=time;result.replay=replay!=0;result.valid=true;
    return result;
}
