#pragma once

// The native actor/state pointers can survive a scene unload. Readiness flags
// identify that resource cycle; pointer identity alone is insufficient.
struct SceneResourceCycle {
    bool requested=false,confirmed=false,initializedSeen=false;
    bool refresh(bool initialized,bool loaded) {
        if(requested&&((initializedSeen&&!initialized)||(confirmed&&!loaded))){
            requested=confirmed=initializedSeen=false;
            return true;
        }
        initializedSeen=initializedSeen||initialized;
        return false;
    }
    void complete(bool initialized,bool ready) {
        initializedSeen=initializedSeen||initialized;
        confirmed=confirmed||ready;
    }
};
