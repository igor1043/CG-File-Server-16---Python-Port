#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
namespace fp {
// FIFA 577DE45C: Player::GetLod (+88) -> descriptor -> vector of 40-byte
// draw records. AddToBuckets (4AF4CE0) tests byte +14 against the player mask.
// A private copy changes draw eligibility only; native mesh/material/bone data
// is never edited and there is therefore no saved mask to restore later.
struct MeshDraw {std::uint8_t bytes[40];};
struct MeshVector {std::uintptr_t begin,end,capacity;std::uint8_t nativeMetadata[0xd0];};
static_assert(sizeof(MeshVector)==0xe8,"Preserve full native mesh wrapper including named-submesh tables");
struct MeshDescriptor {std::uintptr_t vector;std::uint8_t metadata[16];};
struct FilteredHeadMeshes {
    MeshDescriptor descriptor{};MeshVector vector{};MeshDraw rows[64]{};
    unsigned hidden=0;
};
inline bool renderIdentityMatch(int db,int team,int renderDb,int renderTeam,unsigned flags){
    return db>0&&team>=0&&team<2&&db==renderDb&&team==renderTeam&&(flags&1)!=0;
}
inline bool headMeshName(const char* name){
    const char* parts[]={"head","hair","eyes","eye","mouth","teeth","tongue","face","beard"};
    for(const char* part:parts){
        std::size_t i=0;
        while(part[i]&&name[i]){
            char c=name[i];if(c>='A'&&c<='Z')c=static_cast<char>(c+'a'-'A');
            if(c!=part[i])break;
            ++i;
        }
        if(!part[i]){const char c=name[i];if(!c||c=='_'||c=='-'||(c>='0'&&c<='9')||
            // Native low-LOD hair is named hairlod.
            (std::strcmp(part,"hair")==0&&std::strcmp(name+i,"lod")==0))return true;}
    }
    return false;
}
inline bool wantsHiddenHead(int selected,int player,bool enabled,int mode,bool live,int lod){
    return enabled&&mode==0&&live&&selected>=0&&selected<46&&selected==player&&lod>=0&&lod<3;
}
template<class Read>
bool filterHeadMeshes(std::uintptr_t input,FilteredHeadMeshes& out,Read read){
    MeshDescriptor descriptor{};MeshVector vector{};
    if(!input||!read(input,&descriptor,sizeof descriptor)||!descriptor.vector||
       !read(descriptor.vector,&vector,sizeof vector)||vector.end<vector.begin||
       vector.capacity<vector.end||(vector.end-vector.begin)%sizeof(MeshDraw))return false;
    const auto count=(vector.end-vector.begin)/sizeof(MeshDraw);
    if(!count||count>64||!read(vector.begin,out.rows,count*sizeof(MeshDraw)))return false;
    unsigned hidden=0;bool skull=false;
    for(std::size_t i=0;i<count;++i){
        std::uintptr_t name=0;std::memcpy(&name,out.rows[i].bytes+32,sizeof name);
        char text[64]{};
        // Do not accept truncated/unreadable identities.
        if(!name||!read(name,text,sizeof text)||!std::memchr(text,0,sizeof text))return false;
        if(headMeshName(text)){
            out.rows[i].bytes[0x14]=0;++hidden;
            char lower[64]{};std::memcpy(lower,text,sizeof lower);
            for(char& c:lower)if(c>='A'&&c<='Z')c=static_cast<char>(c+'a'-'A');
            if(!std::strncmp(lower,"head",4)||!std::strncmp(lower,"face",4))skull=true;
        }
    }
    if(!hidden||!skull)return false;
    out.hidden=hidden;out.descriptor=descriptor;
    out.vector=vector;
    out.vector.begin=reinterpret_cast<std::uintptr_t>(out.rows);
    out.vector.end=reinterpret_cast<std::uintptr_t>(out.rows+count);
    out.vector.capacity=out.vector.end;
    out.descriptor.vector=reinterpret_cast<std::uintptr_t>(&out.vector);
    // BatchPlayer compares descriptor +0x0c before rebinding cached mesh rows.
    // Distinguish filtered and native descriptors so switching players / F11
    // restores the native list even when its own resource version is unchanged.
    std::uint32_t revision=0;std::memcpy(&revision,out.descriptor.metadata+4,4);
    revision^=0x80000000u;std::memcpy(out.descriptor.metadata+4,&revision,4);
    return true;
}
}
