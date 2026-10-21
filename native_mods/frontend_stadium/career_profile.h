#pragma once
// Mirror the active Career service accessors. The crowd API additionally
// requires statistics/date readiness, which is unrelated to a menu panorama.
template<class Read> static int activeCareerClub(uintptr_t base,Read read){
    auto get=[&](uintptr_t address){uintptr_t value=0;read(address,&value,8);return value;};
    const auto engine=GetModuleHandleW(L"FootballCompEngzf.dll");
    if(!engine||!get(reinterpret_cast<uintptr_t>(engine)+0xb13f0))return 0;
    const auto host=GetModuleHandleW(L"dinput8.dll");
    const auto entry=reinterpret_cast<uintptr_t>(host?GetProcAddress(host,"Fifa16CareerGetState"):nullptr);
    if(!entry)return 0;
    unsigned char code[96]{};
    if(!read(entry,code,sizeof code))return 0;
    const unsigned char marker[]={0x48,0x8d,0x54,0x24,0x50,0x48,0x8d,0x4c,0x24,0x40,0xe8};
    size_t found=sizeof code;
    for(size_t i=0;i+15<=sizeof code;++i)if(!std::memcmp(code+i,marker,sizeof marker)){found=i;break;}
    if(found==sizeof code)return 0;
    int32_t relative=0;std::memcpy(&relative,code+found+11,4);
    const auto live=entry+found+15+relative;
    unsigned char body[64]{},descriptor[24]{},signature[22]{};
    const unsigned char expected[]={0x48,0x63,0x41,0x14,0x83,0xf8,0xff,0x75,0x03,0x31,0xc0,0xc3,0x48,0x69,0xc0,0x18,0x03,0,0,0x48,0x03,0x41};
    if(!read(base+0x5aafff0,signature,sizeof signature)||std::memcmp(signature,expected,sizeof expected)||
       !read(live,body,sizeof body)||!read(base+0x44575e0,descriptor,sizeof descriptor)||descriptor[7]!=0xc7||descriptor[8]!=1)return 0;
    uintptr_t ownerGlobal=0,vtableGlobal=0;
    for(size_t i=0;i+7<=sizeof body;++i){
        if(body[i]!=0x48||body[i+1]!=0x8b)continue;
        std::memcpy(&relative,body+i+3,4);
        if(body[i+2]==0x3d&&!ownerGlobal)ownerGlobal=live+i+7+relative;
        if(body[i+2]==0x35&&!vtableGlobal)vtableGlobal=live+i+7+relative;
    }
    uint32_t index=0;std::memcpy(&index,descriptor+9,4);
    if(!ownerGlobal||!vtableGlobal||index>4096)return 0;
    const auto owner=get(ownerGlobal),vtable=get(vtableGlobal);
    if(!owner||!vtable||get(owner)!=vtable)return 0;
    const auto registry=get(owner+8),wrapper=get(registry+index*32+24),service=get(wrapper);
    int selected=-1;read(service+0x14,&selected,4);
    if(!service||selected<0||selected>=8)return 0;
    const auto contexts=get(service+0x18);
    int team=0;read(contexts+selected*0x318+0x1a4,&team,4);
    return team>0&&team<=2000000?team:0;
}
