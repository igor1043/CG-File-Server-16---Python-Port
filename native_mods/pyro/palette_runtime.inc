// Used only before show emission, after the native batch jobs have completed.
static int paletteHome=0;
static uintptr_t paletteEffect=0;
struct PaletteBinding {uintptr_t property=0,data=0;float previous[4]={},next[4]={};};
static bool palette_property(const char* group,PaletteBinding& binding) {
    uintptr_t manager=0,buckets=0,node=0,groupBegin=0,groupEnd=0;
    unsigned int count=0;
    char path[192]={};_snprintf_s(path,sizeof(path),_TRUNCATE,"PclSys/%s/%s",effectName,group);
    // Prove the named group belongs to our currently retained effect.
    if(!get(activeEffect+0xf8,groupBegin) || !get(activeEffect+0x100,groupEnd) ||
        groupEnd<groupBegin || groupEnd-groupBegin!=11*0x168)return false;
    bool foundGroup=false;
    for(uintptr_t g=groupBegin;g<groupEnd;g+=0x168) {
        uintptr_t name=0;char text[192]={};
        if(!get(g+0x60,name) || !get(name,text))return false;
        text[sizeof(text)-1]=0;
        if(!strcmp(text,path)) {foundGroup=true;break;}
    }
    if(!foundGroup)return false;
    _snprintf_s(path,sizeof(path),_TRUNCATE,"PclSys/%s/%s/ParticleActionRender",effectName,group);
    const unsigned int hash=pyro_attribute_hash("vColorMult",pyro_attribute_hash(path));
    if(!get(image+0x351b120,manager) || !manager || !get(manager+8,buckets) || !buckets ||
        !get(manager+0x10,count) || !count || count>1000000 ||
        !get(buckets+(hash%count)*8,node))return false;
    for(int depth=0;node && depth<128;++depth) {
        unsigned int key=0;uintptr_t next=0;
        if(!get(node,key))return false;
        if(key==hash) {
            int type=0,length=0;
            if(!get(node+8,binding.property) || !binding.property ||
                !get(binding.property+0x3c,type) || type!=8 ||
                !get(binding.property+0x40,length) || length!=1 ||
                !get(binding.property+0x18,binding.data) || !binding.data ||
                !get(binding.data,binding.previous))return false;
            for(int i=0;i<4;++i)if(!(binding.previous[i]>=0 && binding.previous[i]<=4))return false;
            return binding.previous[3]<=1;
        }
        if(!get(node+0x10,next) || next==node)return false;
        node=next;
    }
    return false;
}
static bool palette_write(uintptr_t address,const float (&rgba)[4]) {
    SIZE_T written=0;
    return WriteProcessMemory(GetCurrentProcess(),(void*)address,rgba,sizeof(rgba),&written) && written==sizeof(rgba);
}
static bool apply_home_palette() {
    if(!owned() || !activeEffect || matchHomeTeam<=0)return false;
    if(paletteHome==matchHomeTeam && paletteEffect==activeEffect)return true;
    const TeamPalette* colors=pyro_palette(matchHomeTeam);
    static int missingTeam=0;
    if(!colors) {
        if(missingTeam!=matchHomeTeam) {missingTeam=matchHomeTeam;log_event("PALETTE_UNAVAILABLE show_deferred_no_wrong_team_colors");}
        return false;
    }
    const char* groups[]={"smoke_trail","smoke_trail_overlay","smoke_base","smoke_base_overlay",
        "smoke_black","smoke_black_overlay","confetti_primary","confetti_secondary"};
    PaletteBinding bindings[8]={};
    for(int i=0;i<8;++i) {
        if(!palette_property(groups[i],bindings[i])) {
            static uintptr_t failedEffect=0;
            if(failedEffect!=activeEffect) {
                failedEffect=activeEffect;
                char event[160]={};_snprintf_s(event,sizeof(event),_TRUNCATE,"PALETTE_BIND_FAILED group=%s native_color_storage_unavailable",groups[i]);
                log_event(event);
            }
            return false;
        }
        const bool secondary=(i==4 || i==5 || i==7);
        const unsigned char* rgb=secondary?colors->secondary:colors->primary;
        pyro_palette_rgb(rgb,bindings[i].previous[3],i<6,bindings[i].next);
    }
    if(!owned())return false;
    // Confirm all storage before any mutation. Alpha and existing fade curves remain intact.
    for(int i=0;i<8;++i) {
        uintptr_t data=0;
        if(!get(bindings[i].property+0x18,data) || data!=bindings[i].data)return false;
    }
    for(int i=0;i<8;++i)if(!palette_write(bindings[i].data,bindings[i].next)) {
        for(int j=0;j<=i;++j)palette_write(bindings[j].data,bindings[j].previous);
        return false;
    }
    paletteHome=matchHomeTeam;paletteEffect=activeEffect;
    char event[192]={};_snprintf_s(event,sizeof(event),_TRUNCATE,
        "HOME_PALETTE_APPLIED team=%d primary=%u,%u,%u secondary=%u,%u,%u source=installed_database",
        colors->team,colors->primary[0],colors->primary[1],colors->primary[2],
        colors->secondary[0],colors->secondary[1],colors->secondary[2]);
    log_event(event);return true;
}
