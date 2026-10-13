#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <vector>
#include <string>
#include <map>
#include <memory>
#include <mutex>
#include <algorithm>
#include <cstdio>
#include <cstdint>
#include <cwctype>

struct Shared {
    DWORD version, owner, heartbeat, command, ack, ready, phase, status, error;
    DWORD reads, replaced, cache_count, cache_writes, unsupported;
    wchar_t package[1024];
};
struct MusicShared {
    DWORD version, owner, heartbeat, command, ack, ready, phase, status, error;
    DWORD reads, replaced;
    wchar_t package[1024];
};
using AudioAsset=std::shared_ptr<std::vector<BYTE>>;
struct Profile { std::map<std::wstring,std::map<uint64_t,AudioAsset>> banks; };
static Shared *g_shared;
static MusicShared *g_music_shared;
static std::shared_ptr<Profile> g_profile;
static std::shared_ptr<Profile> g_music_profile;
static std::map<std::wstring,std::shared_ptr<Profile>> g_packages;
static std::mutex g_mutex;
static FILE *g_log;
using Playback=void *(__fastcall *)(void *,void *,void *,void *,DWORD,float,BYTE);
static Playback original_playback;
static bool alive(){return g_shared && g_shared->owner && GetTickCount()-g_shared->heartbeat<5000;}
static bool music_alive(){return g_music_shared && g_music_shared->owner && GetTickCount()-g_music_shared->heartbeat<5000;}
static std::wstring lower(std::wstring s){std::transform(s.begin(),s.end(),s.begin(),towlower);return s;}
static void log_line(const char *s){if(g_log){fprintf(g_log,"%lu %s\n",GetTickCount(),s);fflush(g_log);}}
static std::shared_ptr<Profile> current(){std::lock_guard<std::mutex> lock(g_mutex);return g_profile;}
static std::shared_ptr<Profile> current_music(){std::lock_guard<std::mutex> lock(g_mutex);return g_music_profile;}
static bool read_memory(const void *address,void *dest,size_t size){SIZE_T got=0;return ReadProcessMemory(GetCurrentProcess(),address,dest,size,&got) && got==size;}
static std::wstring bank_path(const void *address){
    char bytes[512];size_t length=0;
    for(;length<sizeof(bytes)-1;++length){if(!read_memory((const BYTE *)address+length,bytes+length,1))return L"";if(!bytes[length])break;}
    if(length==sizeof(bytes)-1)return L"";
    std::wstring path;
    for(size_t i=0;i<length;++i){unsigned char c=bytes[i];if(c>=128)return L"";path+=c=='\\'?L'/':wchar_t(c);}
    path=lower(path);
    auto speech=path.find(L"audiodata/speechdata/por_br/");
    auto music=path.find(L"audiodata/sfx/intromusic_");
    if(speech==std::wstring::npos && music==std::wstring::npos)return L"";
    auto pos=speech==std::wstring::npos?music:music==std::wstring::npos?speech:std::min(speech,music);
    return path.substr(pos);
}
static void *__fastcall redirected_playback(void *description,void *arg2,void *arg3,void *player,DWORD arg5,float arg6,BYTE arg7){
    BYTE copy[80];
    if(read_memory(description,copy,sizeof(copy))){
        const void *path=nullptr;uint64_t offset=0;memcpy(&path,copy+0x30,8);memcpy(&offset,copy+8,8);
        auto key=bank_path(path);
        if(key.rfind(L"audiodata/sfx/intromusic_",0)==0){
            auto profile=current_music();
            if(music_alive() && profile){
                auto bank=profile->banks.find(key);
                if(bank!=profile->banks.end()){
                    InterlockedIncrement((LONG *)&g_music_shared->reads);auto sample=bank->second.find(offset);
                    if(sample!=bank->second.end()){
                        const void *resident=sample->second->data();uint64_t zero=0;
                        memcpy(copy+0x18,&resident,8);memcpy(copy+8,&zero,8);memcpy(copy+0x30,&zero,8);copy[0x44]=1;
                        InterlockedIncrement((LONG *)&g_music_shared->replaced);
                        return original_playback(copy,arg2,arg3,player,arg5,arg6,arg7);
                    }
                }
            }
        }else if(key.rfind(L"audiodata/speechdata/por_br/",0)==0){
            auto profile=current();
            if(alive() && profile && !profile->banks.empty()){
                auto bank=profile->banks.find(key);
                if(bank!=profile->banks.end()){
                    InterlockedIncrement((LONG *)&g_shared->reads);auto sample=bank->second.find(offset);
                    if(sample!=bank->second.end()){
                        const void *resident=sample->second->data();uint64_t zero=0;
                        // The resident SPS header carries the replacement's full duration.
                        memcpy(copy+0x18,&resident,8);memcpy(copy+8,&zero,8);memcpy(copy+0x30,&zero,8);copy[0x44]=1;
                        InterlockedIncrement((LONG *)&g_shared->replaced);
                        return original_playback(copy,arg2,arg3,player,arg5,arg6,arg7);
                    }
                }
            }
        }
    }
    return original_playback(description,arg2,arg3,player,arg5,arg6,arg7);
}
static bool install_playback_hook(){
    BYTE *module=(BYTE *)GetModuleHandleW(nullptr),*site=module+0x3c866c1,*target=module+0x3c30c90;
    const BYTE expected_call[]={0xe8,0xca,0xa5,0xfa,0xff};
    const BYTE expected_target[]={0x53,0x48,0x83,0xec,0x20,0x48,0x83,0x79,0x18,0,0x4c,0x89,0xcb,0x75,0x44};
    // Both signatures were verified in live FIFA16 RAM. Other builds are
    // refused before modifying executable code.
    BYTE call_bytes[5],target_bytes[sizeof(expected_target)];
    if(!read_memory(site,call_bytes,5) || !read_memory(target,target_bytes,sizeof(target_bytes)) || memcmp(call_bytes,expected_call,5) || memcmp(target_bytes,expected_target,sizeof(target_bytes)))return false;
    BYTE *relay=nullptr;uintptr_t origin=(uintptr_t)site&~uintptr_t(65535);
    for(uintptr_t distance=65536;distance<0x70000000 && !relay;distance+=65536){
        for(int direction:{1,-1}){
            if(direction<0 && distance>origin)continue;
            uintptr_t candidate=direction>0?origin+distance:origin-distance;
            relay=(BYTE *)VirtualAlloc((void *)candidate,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);if(relay)break;
        }
    }
    if(!relay)return false;
    BYTE jump[]={0xff,0x25,0,0,0,0};memcpy(relay,jump,6);void *destination=(void *)redirected_playback;memcpy(relay+6,&destination,8);
    DWORD old=0,ignored=0;
    if(!VirtualProtect(relay,4096,PAGE_EXECUTE_READ,&old)){VirtualFree(relay,0,MEM_RELEASE);return false;}
    FlushInstructionCache(GetCurrentProcess(),relay,14);original_playback=(Playback)target;
    BYTE call[5]={0xe8};int32_t displacement=(int32_t)(relay-(site+5));memcpy(call+1,&displacement,4);
    if(!VirtualProtect(site,5,PAGE_EXECUTE_READWRITE,&old)){VirtualFree(relay,0,MEM_RELEASE);return false;}
    memcpy(site,call,5);FlushInstructionCache(GetCurrentProcess(),site,5);VirtualProtect(site,5,old,&ignored);return true;
}
struct Reader{
    std::vector<BYTE> data;size_t pos=0;
    template<class T>T get(){if(pos+sizeof(T)>data.size())throw 1;T value;memcpy(&value,data.data()+pos,sizeof(T));pos+=sizeof(T);return value;}
    std::vector<BYTE> bytes(DWORD size){if(size>64*1024*1024 || size>data.size()-pos)throw 1;std::vector<BYTE> value(data.begin()+pos,data.begin()+pos+size);pos+=size;return value;}
    std::wstring path(){DWORD size=get<DWORD>();if(size>1024)throw 1;auto value=bytes(size*2);return std::wstring((wchar_t *)value.data(),size);}
};
static std::shared_ptr<Profile> load(const wchar_t *path,bool music=false){
    WIN32_FILE_ATTRIBUTE_DATA attributes={};
    if(!GetFileAttributesExW(path,GetFileExInfoStandard,&attributes))throw 2;
    auto key=(music?L"music|":L"speech|")+lower(path)+L"|"+std::to_wstring(attributes.ftLastWriteTime.dwHighDateTime)+L"|"+std::to_wstring(attributes.ftLastWriteTime.dwLowDateTime)+L"|"+std::to_wstring(attributes.nFileSizeLow);
    auto cached=g_packages.find(key);if(cached!=g_packages.end())return cached->second;
    FILE *file=nullptr;_wfopen_s(&file,path,L"rb");if(!file)throw 2;
    _fseeki64(file,0,SEEK_END);auto size=_ftelli64(file);_fseeki64(file,0,SEEK_SET);if(size<12 || size>512*1024*1024){fclose(file);throw 3;}
    Reader r;r.data.resize((size_t)size);if(fread(r.data.data(),1,r.data.size(),file)!=r.data.size()){fclose(file);throw 4;}fclose(file);
    auto magic=r.get<uint64_t>();bool pooled=magic==0x00334b504e363146ull;
    if(!pooled && magic!=0x00324b504e363146ull)throw 5; // F16NPK2/3
    auto validate=[](const std::vector<BYTE>& bytes) {
        if(bytes.size()<12 || bytes[0]!=0x48)throw 9;
        size_t pos=0;bool ended=false;
        while(pos+4<=bytes.size()){
            DWORD block=(DWORD(bytes[pos])<<24)|(DWORD(bytes[pos+1])<<16)|(DWORD(bytes[pos+2])<<8)|bytes[pos+3];
            DWORD length=block&0xffffff;BYTE type=block>>24;
            if(type==0x45){length=std::max<DWORD>(4,length);ended=pos+length==bytes.size();break;}
            if(length<4 || length>bytes.size()-pos)throw 9;pos+=length;
        }
        if(!ended)throw 9;
    };
    std::vector<AudioAsset> pool;
    if(pooled){
        DWORD count=r.get<DWORD>();if(count>100000)throw 6;pool.reserve(count);
        for(DWORD i=0;i<count;++i){auto bytes=r.bytes(r.get<DWORD>());validate(bytes);pool.push_back(std::make_shared<std::vector<BYTE>>(std::move(bytes)));}
    }
    DWORD count=r.get<DWORD>();if(count>64)throw 6;auto profile=std::make_shared<Profile>();
    for(DWORD i=0;i<count;++i){
        auto bank=lower(r.path());
        if(music){
            if(bank.rfind(L"audiodata/sfx/intromusic_",0)!=0 || bank.find(L"..")!=std::wstring::npos || bank.find(L".sbs")==std::wstring::npos)throw 7;
        }else if(bank.rfind(L"audiodata/speechdata/por_br/",0)!=0)throw 7;
        DWORD samples=r.get<DWORD>();if(samples>100000 || profile->banks.count(bank))throw 8;auto &assets=profile->banks[bank];
        for(DWORD j=0;j<samples;++j){
            uint64_t offset=r.get<uint64_t>();if(assets.count(offset))throw 9;
            if(pooled){DWORD index=r.get<DWORD>();if(index>=pool.size())throw 9;assets.emplace(offset,pool[index]);}
            else {auto bytes=r.bytes(r.get<DWORD>());validate(bytes);assets.emplace(offset,std::make_shared<std::vector<BYTE>>(std::move(bytes)));}
        }
    }
    if(r.pos!=r.data.size())throw 11;g_packages[key]=profile;return profile;
}
static DWORD WINAPI worker(void *){
    wchar_t root[32768];GetModuleFileNameW(nullptr,root,32768);auto slash=wcsrchr(root,L'\\');if(slash)slash[1]=0;
    _wfopen_s(&g_log,(std::wstring(root)+L"runtime\\narration_redirect.log").c_str(),L"a");
    bool installed=install_playback_hook();log_line(installed?"Resident speech playback hook installed":"FIFA build signature mismatch; no hook installed");
    DWORD observed_owner=0,observed_music_owner=0;
    while(true){
        if(!g_shared){HANDLE map=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,L"Local\\FIFA16_Narration_v1");if(map){g_shared=(Shared *)MapViewOfFile(map,FILE_MAP_ALL_ACCESS,0,0,sizeof(Shared));CloseHandle(map);}}
        if(!g_music_shared){HANDLE map=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,L"Local\\FIFA16_IntroMusic_v1");if(map){g_music_shared=(MusicShared *)MapViewOfFile(map,FILE_MAP_ALL_ACCESS,0,0,sizeof(MusicShared));CloseHandle(map);}}
        if(g_shared && g_shared->version==1){
            g_shared->ready=installed?1:0;
            if(!alive() || observed_owner!=g_shared->owner){std::lock_guard<std::mutex> lock(g_mutex);g_profile.reset();observed_owner=g_shared->owner;}
            if(installed && alive() && g_shared->command!=g_shared->ack){DWORD command=g_shared->command;g_shared->status=1;g_shared->error=0;
                try{
                    if(g_shared->phase!=1)throw 12;auto profile=load(g_shared->package);
                    {std::lock_guard<std::mutex> lock(g_mutex);
                        // The resident decoder retains raw SPS pointers. Keep
                        // selected assets alive for the game's lifetime.
                        g_profile=profile;
                    }
                    g_shared->status=2;log_line("Narration selected; full resident SPS assets active");
                }catch(int error){g_shared->error=error;g_shared->status=3;log_line("Narration profile rejected");}
                 catch(...){g_shared->error=20;g_shared->status=3;log_line("Narration load failed");}
                g_shared->ack=command;
            }
        }
        if(g_music_shared && g_music_shared->version==1){
            g_music_shared->ready=installed?1:0;
            if(!music_alive() || observed_music_owner!=g_music_shared->owner){
                std::lock_guard<std::mutex> lock(g_mutex);g_music_profile.reset();observed_music_owner=g_music_shared->owner;
            }
            if(installed && music_alive() && g_music_shared->command!=g_music_shared->ack){
                DWORD command=g_music_shared->command;g_music_shared->status=1;g_music_shared->error=0;
                try{
                    if(g_music_shared->phase!=1)throw 12;
                    if(!g_music_shared->package[0]){
                        {std::lock_guard<std::mutex> lock(g_mutex);g_music_profile.reset();}
                        g_music_shared->status=2;log_line("Intro music cleared; original game banks active");
                    }else{
                        auto profile=load(g_music_shared->package,true);
                        if(profile->banks.empty())throw 9;
                        {std::lock_guard<std::mutex> lock(g_mutex);g_music_profile=profile;}
                        g_music_shared->status=2;log_line("Intro music profile selected; external SPS assets active");
                    }
                }catch(int error){g_music_shared->error=error;g_music_shared->status=3;log_line("Intro music profile rejected");}
                 catch(...){g_music_shared->error=20;g_music_shared->status=3;log_line("Intro music profile load failed");}
                g_music_shared->ack=command;
            }
        }
        Sleep(50);
    }
}
BOOL APIENTRY DllMain(HMODULE dll,DWORD reason,LPVOID){if(reason==DLL_PROCESS_ATTACH){DisableThreadLibraryCalls(dll);HANDLE thread=CreateThread(nullptr,0,worker,nullptr,0,nullptr);if(thread)CloseHandle(thread);}return TRUE;}
