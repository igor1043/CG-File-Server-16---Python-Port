#pragma once
// Mirror the active Career service accessors. The crowd API additionally
// requires statistics/date readiness, which is unrelated to a menu panorama.
template<class Read> static int activeCareerClub(uintptr_t base,Read read,bool* resolved=nullptr){
    if(resolved)*resolved=false;
    auto get=[&](uintptr_t address){uintptr_t value=0;read(address,&value,8);return value;};
    const auto engine=GetModuleHandleW(L"FootballCompEngzf.dll");
    if(!engine){if(resolved)*resolved=true;return 0;}
    if(!get(reinterpret_cast<uintptr_t>(engine)+0xb13f0))return 0;
    const auto host=GetModuleHandleW(L"dinput8.dll");
    struct ContextRead {
        uint32_t schema,size,sequence,pid;
        uintptr_t service,vtable,registry;
        uint32_t epoch,ownerThread;
    };
    static_assert(sizeof(ContextRead)==48,"Published career identity ABI");
    const auto published=reinterpret_cast<uintptr_t>(host?GetProcAddress(host,"Fifa16CareerContextRead"):nullptr);
    if(published){
        ContextRead identity{},check{};unsigned char descriptor[24]{},signature[22]{};
        const unsigned char expected[]={0x48,0x63,0x41,0x14,0x83,0xf8,0xff,0x75,0x03,0x31,0xc0,0xc3,0x48,0x69,0xc0,0x18,0x03,0,0,0x48,0x03,0x41};
        if(!read(published,&identity,sizeof identity)||identity.schema!=1||identity.size!=sizeof identity||
           identity.sequence&1||identity.pid!=GetCurrentProcessId()||!identity.service||!identity.registry||!identity.vtable||
           !read(base+0x5aafff0,signature,sizeof signature)||std::memcmp(signature,expected,sizeof expected)||
           !read(base+0x44575e0,descriptor,sizeof descriptor)||descriptor[7]!=0xc7||descriptor[8]!=1)return 0;
        uint32_t index=0;std::memcpy(&index,descriptor+9,4);
        if(index>4096||get(get(identity.registry+index*32+24))!=identity.service||get(identity.service)!=identity.vtable)return 0;
        int selected=-1;if(!read(identity.service+0x14,&selected,4)||selected < -1||selected>=8)return 0;
        int team=0;
        if(selected>=0){const auto contexts=get(identity.service+0x18);if(!contexts||!read(contexts+selected*0x318+0x1a4,&team,4)||team<=0||team>2000000)return 0;}
        if(!read(published,&check,sizeof check)||std::memcmp(&identity,&check,sizeof identity))return 0;
        if(resolved)*resolved=true;
        return team;
    }
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
    int selected=-1;if(!service||!read(service+0x14,&selected,4))return 0;
    if(selected==-1){if(resolved)*resolved=true;return 0;}
    if(selected<0||selected>=8)return 0;
    const auto contexts=get(service+0x18);
    int team=0;if(!contexts||!read(contexts+selected*0x318+0x1a4,&team,4)||team<=0||team>2000000)return 0;
    if(resolved)*resolved=true;
    return team>0&&team<=2000000?team:0;
}
