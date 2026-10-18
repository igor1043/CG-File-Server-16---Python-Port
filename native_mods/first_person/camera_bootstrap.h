#pragma once

namespace fp {
// FIFA 577DE45C sets this flag only after its normal game thread has built
// the bone-name cache (RVA 44D7870..44D79E7). Calling the resolver earlier
// lazily initializes that cache against a missing registry and crashes FIFA.
static constexpr unsigned long long boneCacheReadyRva=0x3518200;
template<class Lookup>
bool initializedBones(unsigned char ready,Lookup lookup,int& head,int& root){
    if(ready!=1)return false;
    const int h=lookup(3),r=lookup(11);
    if(h<0||h>255||r<0||r>255)return false;
    head=h;root=r;return true;
}
}
