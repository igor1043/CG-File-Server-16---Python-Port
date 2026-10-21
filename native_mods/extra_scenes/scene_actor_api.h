#pragma once
#include <stdint.h>
// Read-only snapshot, published on the existing SLE scene callback.
// No consumer invokes an actor, animation, resource loader or Lua callback.
struct SceneActorSnapshot {
 uint32_t version=1,size=sizeof(SceneActorSnapshot);
 uint64_t tick=0,renderer=0;
 uint32_t generation=0,home=0;
 int32_t mascotValid=0,reserved=0;
 float mascotPosition[3]{},mascotHead[16]{};
};
static_assert(sizeof(SceneActorSnapshot)==120,"Versioned scene snapshot ABI");
