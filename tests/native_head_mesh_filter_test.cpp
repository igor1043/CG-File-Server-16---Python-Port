#include "../native_mods/first_person/head_mesh_filter.h"
#include <cassert>
#include <cstdio>
#include <array>
struct Fixture {
    fp::MeshDraw rows[12]{};
    fp::MeshVector vector{};fp::MeshDescriptor descriptor{};
    char names[12][64]{};
    Fixture(){
        const char* labels[]={"jersey_noarmband","arms","shorts","shoes","socks","legs",
            "head","eyes","hair1","hair2","mouth","teeth"};
        for(int i=0;i<12;++i){std::memcpy(names[i],labels[i],std::strlen(labels[i])+1);const auto name=reinterpret_cast<std::uintptr_t>(names[i]);
            std::memcpy(rows[i].bytes+32,&name,8);rows[i].bytes[0x14]=static_cast<std::uint8_t>(i+1);}
        vector={reinterpret_cast<std::uintptr_t>(rows),reinterpret_cast<std::uintptr_t>(rows+12),reinterpret_cast<std::uintptr_t>(rows+12)};
        descriptor.vector=reinterpret_cast<std::uintptr_t>(&vector);descriptor.metadata[0]=7;
    }
    bool read(std::uintptr_t at,void* out,std::size_t n)const{
        const auto begin=reinterpret_cast<std::uintptr_t>(this);
        if(at<begin||at>begin+sizeof *this||n>begin+sizeof *this-at)return false;
        std::memcpy(out,reinterpret_cast<const void*>(at),n);return true;
    }
};
int main(){
    // Pedro: simulation index 9, live render slot 17; preview slot 3 is inactive.
    assert(fp::renderIdentityMatch(233605,0,233605,0,0x11));
    assert(!fp::renderIdentityMatch(233605,0,233605,0,0x10));
    assert(!fp::renderIdentityMatch(233605,0,233605,1,0x11));
    assert(!fp::renderIdentityMatch(233605,0,225964,0,0x11));
    static_assert(sizeof(fp::MeshDraw)==40&&sizeof(fp::MeshDescriptor)==24&&sizeof(fp::MeshVector)==0xe8);
    Fixture a,b;std::array<unsigned char,sizeof(Fixture)> before{};std::memcpy(before.data(),&a,sizeof a);
    fp::FilteredHeadMeshes copy{};
    for(unsigned i=0;i<sizeof a.vector.nativeMetadata;++i)a.vector.nativeMetadata[i]=static_cast<unsigned char>(i+1);
    // Named mesh lookup indexes wrapper +58/+60, which the v10 24-byte copy lost.
    const auto nativeTable=reinterpret_cast<std::uintptr_t>(a.names);
    std::memcpy(reinterpret_cast<unsigned char*>(&a.vector)+0x58,&nativeTable,8);
    std::memcpy(reinterpret_cast<unsigned char*>(&a.vector)+0x60,&nativeTable,8);
    std::memcpy(before.data(),&a,sizeof a);
    const auto select=[&](int selected,int player,bool enabled=true,int mode=0,bool live=true,int lod=0){
        auto& fixture=player==3?a:b;
        const auto original=&fixture.descriptor;
        if(!fp::wantsHiddenHead(selected,player,enabled,mode,live,lod))return original;
        const bool ok=fp::filterHeadMeshes(reinterpret_cast<std::uintptr_t>(original),copy,
            [&](auto at,auto out,auto n){return fixture.read(at,out,n);});assert(ok);return &copy.descriptor;
    };
    assert(select(3,3)==&copy.descriptor&&copy.hidden==6);
    assert(copy.descriptor.metadata[0]==7);
    assert(std::memcmp(copy.vector.nativeMetadata,a.vector.nativeMetadata,sizeof a.vector.nativeMetadata)==0);
    std::uintptr_t named=0;std::memcpy(&named,reinterpret_cast<unsigned char*>(&copy.vector)+0x58,8);assert(named==nativeTable);
    std::uint32_t originalVersion=0,copyVersion=0;
    std::memcpy(&originalVersion,a.descriptor.metadata+4,4);std::memcpy(&copyVersion,copy.descriptor.metadata+4,4);
    assert(originalVersion!=copyVersion&&originalVersion==(copyVersion^0x80000000u));
    for(int i=0;i<12;++i)assert(copy.rows[i].bytes[0x14]==(i<6?i+1:0));
    assert(std::memcmp(before.data(),&a,sizeof a)==0); // Every original byte survives.
    // Transfer to a new player; the prior player receives the exact native list.
    for(int i=0;i<2000;++i){
        assert(select(4,3)==&a.descriptor);assert(select(4,4)==&copy.descriptor);
        assert(select(3,4)==&b.descriptor);assert(select(3,3)==&copy.descriptor);
    }
    assert(std::memcmp(before.data(),&a,sizeof a)==0);
    assert(select(3,3,false)==&a.descriptor); // F10 / Disable / Server disconnect.
    assert(select(3,3,true,1)==&a.descriptor); // Third person.
    assert(select(3,3,true,0,false)==&a.descriptor); // Replay / stale camera.
    assert(select(3,3,true,0,true,3)==&a.descriptor); // Keep native body shadow.
    assert(select(-1,3)==&a.descriptor);
    for(const char* s:{"head","Head_lod","eyes","eye_l","mouth","teeth","tongue","hairlod","hair2","beard"})assert(fp::headMeshName(s));
    for(const char* s:{"arms","bodyskinlod","jersey","shoes","headlight","eyebrowshirt"})assert(!fp::headMeshName(s));
    auto bad=a.descriptor;bad.vector=0;
    assert(!fp::filterHeadMeshes(reinterpret_cast<std::uintptr_t>(&bad),copy,[](auto,auto,auto){return false;}));
    a.vector.end=a.vector.begin+1;
    assert(!fp::filterHeadMeshes(reinterpret_cast<std::uintptr_t>(&a.descriptor),copy,[&](auto at,auto out,auto n){return a.read(at,out,n);}));
    std::puts("PASS: head/eyes/mouth/hair private draw copies, body unchanged, 4000 selection transfers, native restore on disable/replay/third-person, shadow retained, invalid data rejected");
}
