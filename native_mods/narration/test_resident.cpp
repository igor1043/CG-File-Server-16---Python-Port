#include "narration_resident.cpp"
#include <cassert>
static const BYTE *expected_asset;
static bool should_replace;
static void *expected_original;
static void *__fastcall fake_playback(void *description,void *a,void *b,void *c,DWORD d,float e,BYTE f){
    assert(a==(void *)1 && b==(void *)2 && c==(void *)3 && d==42 && e==0.25f && f==7);
    if(should_replace){
        assert(*(const BYTE **)((BYTE *)description+0x18)==expected_asset);
        assert(*(uint64_t *)((BYTE *)description+8)==0);
        assert(*(uint64_t *)((BYTE *)description+0x30)==0);
        assert(((BYTE *)description)[0x44]==1);
    }else assert(description==expected_original);
    return (void *)0x1234;
}
int wmain(int argc,wchar_t **argv){
    Shared shared={};shared.owner=GetCurrentProcessId();shared.heartbeat=GetTickCount();g_shared=&shared;original_playback=fake_playback;
    auto p=std::make_shared<Profile>();std::string path="audiodata/speechdata/por_br/DEMO.sbs";
    auto &asset=p->banks[L"audiodata/speechdata/por_br/demo.sbs"][32];asset=std::make_shared<std::vector<BYTE>>(250000,0x48);expected_asset=asset->data();g_profile=p;
    BYTE descriptor[80]={};const char *ptr=path.c_str();uint64_t offset=32;memcpy(descriptor+8,&offset,8);memcpy(descriptor+0x30,&ptr,8);expected_original=descriptor;
    BYTE untouched[80];memcpy(untouched,descriptor,80);should_replace=true;
    assert(redirected_playback(descriptor,(void *)1,(void *)2,(void *)3,42,0.25f,7)==(void *)0x1234);
    assert(!memcmp(untouched,descriptor,80) && shared.replaced==1);
    should_replace=false;offset=999;memcpy(descriptor+8,&offset,8);
    redirected_playback(descriptor,(void *)1,(void *)2,(void *)3,42,0.25f,7);
    shared.owner=0;offset=32;memcpy(descriptor+8,&offset,8);
    redirected_playback(descriptor,(void *)1,(void *)2,(void *)3,42,0.25f,7);
    puts("resident playback: long asset, unchanged descriptor, forwarded arguments and original fallback OK");
    for(int i=1;i<argc;++i){
        try{auto profile=load(argv[i]);size_t samples=0;for(auto &bank:profile->banks)samples+=bank.second.size();printf("package validation: %zu banks, %zu complete SPS samples OK\n",profile->banks.size(),samples);assert(load(argv[i])==profile);}
        catch(int error){printf("package validation FAILED error=%d\n",error);return 1;}
    }
}
