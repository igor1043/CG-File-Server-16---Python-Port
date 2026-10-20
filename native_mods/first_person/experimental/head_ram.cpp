#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <intrin.h>
#include <cstdint>
#include <cstring>
#include <cmath>
#include "../camera_protocol.h"
#include "../camera_channel.h"
#include "../head_mesh_filter.h"
static uintptr_t image,bc;
static volatile LONG started=0,stopping=0,on=1,wanted=-1,backCm=0;
static volatile LONG64 lease=0,meshTick=0;
using Generator=void(__fastcall*)(void*,void*);
using GetLod=void*(__fastcall*)(void*,int);
static Generator previousGenerator;
static GetLod originalLod;
static CameraPublicState* camera;
static CameraChannel* channel;
static HANDLE mapping;
extern "C" {__declspec(dllexport) struct RamState {
    uint32_t version=1,size=sizeof(RamState);
    int32_t enabled=1,selected=-1,slot=-1,lod=-1,hidden=0,back=0;
    int64_t copies=0,passes=0,restores=0,repositions=0;
    float before[3]{},after[3]{};
} HeadRamStatus{};}
static bool read(uintptr_t a,void* p,size_t n){
    if(a<0x10000||a>UINTPTR_MAX-n)return false;
    __try {std::memcpy(p,reinterpret_cast<void*>(a),n);return true;}
    __except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T>static T get(uintptr_t a){T x{};read(a,&x,sizeof x);return x;}
static bool swap(uintptr_t slot,uintptr_t from,uintptr_t to){
    DWORD old=0;if(!VirtualProtect(reinterpret_cast<void*>(slot),8,PAGE_READWRITE,&old))return false;
    auto before=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),reinterpret_cast<void*>(to),reinterpret_cast<void*>(from));
    DWORD ignored=0;VirtualProtect(reinterpret_cast<void*>(slot),8,old,&ignored);return before==reinterpret_cast<void*>(from);
}
static bool active(){
    return !stopping&&on&&channel&&camera&&channel->owner&&channel->version==4&&channel->requested==1&&channel->enabled==1&&
        channel->mode==0&&static_cast<uint32_t>(GetTickCount()-channel->heartbeat)<1500&&camera->enabled&&camera->started&&!camera->stopping;
}
static int renderSlot(uintptr_t object,int selected){
    if(selected<0||selected>=46||!object||get<uintptr_t>(object)!=image+0x2207230)return -1;
    auto impl=get<uintptr_t>(object+0x18);if(!impl)return -1;
    int slot=get<int>(impl);if(slot<0||slot>=58||get<uintptr_t>(image+0x34fbf70+static_cast<uintptr_t>(slot)*8)!=object)return -1;
    auto manager=get<uintptr_t>(image+0x3517420),game=get<uintptr_t>(manager+0x10);if(!game)return -1;
    int seq=get<int>(game+0xda840);if(seq<0)return -1;
    auto players=get<uintptr_t>(game+static_cast<uintptr_t>(seq%10)*0x15da0+0xca0);if(!players)return -1;
    auto player=get<uintptr_t>(players+static_cast<uintptr_t>(selected)*8);if(!player||get<int>(player)!=selected)return -1;
    auto map=image+0x34fbda0+static_cast<uintptr_t>(slot)*8;
    return fp::renderIdentityMatch(get<int>(player+8),get<int>(player+4),get<int>(map),get<int>(map+4),get<unsigned>(impl+0x80))?slot:-1;
}
static void* __fastcall lodHook(void* self,int lod){
    void* original=originalLod(self,lod);
    // This exact call site binds main-view mesh rows and metadata. Material
    // setup, other views and shadow LOD 3 always receive original descriptors.
    if(reinterpret_cast<uintptr_t>(_ReturnAddress())!=image+0x43be214)return original;
    InterlockedIncrement64(&HeadRamStatus.passes);
    const int selected=InterlockedCompareExchange(&wanted,0,0);
    if(lod<0||lod>2||!active()||GetTickCount64()-static_cast<ULONGLONG>(lease)>100){
        InterlockedIncrement64(&HeadRamStatus.restores);return original;
    }
    int slot=renderSlot(reinterpret_cast<uintptr_t>(self),selected);
    if(slot<0){InterlockedIncrement64(&HeadRamStatus.restores);return original;}
    // Persistent per-render-thread storage; never shared or released while a
    // BatchPlayer cache can refer to it, even after Stop.
    static thread_local fp::FilteredHeadMeshes copies[58][3];
    auto& copy=copies[slot][lod];
    if(!fp::filterHeadMeshes(reinterpret_cast<uintptr_t>(original),copy,read))return original;
    HeadRamStatus.selected=selected;HeadRamStatus.slot=slot;HeadRamStatus.lod=lod;HeadRamStatus.hidden=static_cast<int>(copy.hidden);
    InterlockedIncrement64(&HeadRamStatus.copies);
    InterlockedExchange64(&meshTick,static_cast<LONG64>(GetTickCount64()));
    return &copy.descriptor;
}
static void __fastcall cameraHook(void* self,void* output){
    previousGenerator(self,output);
    const auto behavior=reinterpret_cast<uintptr_t>(self);const int selected=get<int>(behavior+0x9cc),phase=get<int>(behavior+0xaa4);
    if(!active()||selected<0||selected>=46||(phase!=2&&phase!=14&&phase!=15)){
        InterlockedExchange(&wanted,-1);return;
    }
    float p[28]{};if(!read(reinterpret_cast<uintptr_t>(output),p,sizeof p))return;
    // v11 writes a one-metre-normalized sight line (1000 FIFA cm) and near=2.
    // Reject native/invalid outputs rather than translating a different camera.
    const float x=p[4]-p[0],y=p[5]-p[1],z=p[6]-p[2],length=std::sqrt(x*x+y*y+z*z);
    if(p[14]!=2.f||!std::isfinite(length)||std::fabs(length-1000.f)>1.f){InterlockedExchange(&wanted,-1);return;}
    InterlockedExchange(&wanted,selected);InterlockedExchange64(&lease,static_cast<LONG64>(GetTickCount64()));
    const int back=InterlockedCompareExchange(&backCm,0,0);HeadRamStatus.back=back;
    if(back<=0||HeadRamStatus.selected!=selected||GetTickCount64()-static_cast<ULONGLONG>(meshTick)>100)return;
    const float delta[3]={x*back/length,y*back/length,z*back/length};
    for(int i=0;i<3;++i){HeadRamStatus.before[i]=p[i];p[i]-=delta[i];p[i+4]-=delta[i];HeadRamStatus.after[i]=p[i];}
    std::memcpy(output,p,sizeof p);std::memcpy(reinterpret_cast<void*>(behavior+0xbe0),p,0x64);
    InterlockedIncrement64(&HeadRamStatus.repositions);
}
static DWORD WINAPI watchdog(void*){
    while(!stopping){
        DWORD pid=0;GetWindowThreadProcessId(GetForegroundWindow(),&pid);
        if(pid==GetCurrentProcessId()&&(GetAsyncKeyState(VK_F11)&0x8000)){
            InterlockedExchange(&on,0);InterlockedExchange(&wanted,-1);InterlockedExchange(&backCm,0);
        }
        HeadRamStatus.enabled=on?1:0;Sleep(25);
    }return 0;
}
extern "C" __declspec(dllexport) DWORD WINAPI Start(void*){
    if(started)return stopping?0:1;
    image=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));bc=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"BCEnginezf.dll"));
    auto v11=GetModuleHandleW(L"server16_first_person_v11.dll");if(!v11||!bc)return 0;
    camera=reinterpret_cast<CameraPublicState*>(GetProcAddress(v11,"CameraStatus"));if(!camera||!camera->started||camera->stopping)return 0;
    previousGenerator=reinterpret_cast<Generator>(get<uintptr_t>(bc+0x1254f0));originalLod=reinterpret_cast<GetLod>(image+0x437b400);
    MEMORY_BASIC_INFORMATION mbi{};
    if(!VirtualQuery(reinterpret_cast<void*>(previousGenerator),&mbi,sizeof mbi)||mbi.AllocationBase!=v11||get<uintptr_t>(image+0x22072b8)!=reinterpret_cast<uintptr_t>(originalLod))return 0;
    const unsigned char code[]={0x48,0x8b,0x41,0x18,0x48,0x63,0xd2,0x48,0x8b,0x44,0xd0,0x08,0xc3};unsigned char actual[sizeof code]{};
    if(!read(image+0x437b400,actual,sizeof actual)||std::memcmp(code,actual,sizeof code))return 0;
    mapping=OpenFileMappingW(FILE_MAP_READ,FALSE,CAMERA_MAPPING_NAME);if(!mapping)return 0;
    channel=static_cast<CameraChannel*>(MapViewOfFile(mapping,FILE_MAP_READ,0,0,sizeof(CameraChannel)));if(!channel)return 0;
    HMODULE pin=nullptr;if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCWSTR>(&image),&pin))return 0;
    if(!swap(image+0x22072b8,reinterpret_cast<uintptr_t>(originalLod),reinterpret_cast<uintptr_t>(&lodHook)))return 0;
    if(!swap(bc+0x1254f0,reinterpret_cast<uintptr_t>(previousGenerator),reinterpret_cast<uintptr_t>(&cameraHook))){swap(image+0x22072b8,reinterpret_cast<uintptr_t>(&lodHook),reinterpret_cast<uintptr_t>(originalLod));return 0;}
    auto thread=CreateThread(nullptr,0,watchdog,nullptr,0,nullptr);
    if(!thread){swap(image+0x22072b8,reinterpret_cast<uintptr_t>(&lodHook),reinterpret_cast<uintptr_t>(originalLod));swap(bc+0x1254f0,reinterpret_cast<uintptr_t>(&cameraHook),reinterpret_cast<uintptr_t>(previousGenerator));return 0;}
    CloseHandle(thread);InterlockedExchange(&started,1);return 1;
}
extern "C" __declspec(dllexport) DWORD WINAPI Enable(void*){if(stopping)return 0;InterlockedExchange(&on,1);return 1;}
extern "C" __declspec(dllexport) DWORD WINAPI Disable(void*){InterlockedExchange(&on,0);InterlockedExchange(&wanted,-1);InterlockedExchange(&backCm,0);return 1;}
extern "C" __declspec(dllexport) DWORD WINAPI SetBackCm(void* value){
    if(!value||stopping)return 0;int cm=get<int>(reinterpret_cast<uintptr_t>(value));if(cm<0||cm>20)return 0;
    InterlockedExchange(&backCm,cm);return 1;
}
extern "C" __declspec(dllexport) DWORD WINAPI Stop(void*){
    InterlockedExchange(&on,0);InterlockedExchange(&wanted,-1);InterlockedExchange(&backCm,0);InterlockedExchange(&stopping,1);
    bool a=swap(image+0x22072b8,reinterpret_cast<uintptr_t>(&lodHook),reinterpret_cast<uintptr_t>(originalLod));
    bool b=swap(bc+0x1254f0,reinterpret_cast<uintptr_t>(&cameraHook),reinterpret_cast<uintptr_t>(previousGenerator));return a&&b?1:0;
}
BOOL WINAPI DllMain(HINSTANCE,DWORD,LPVOID){return TRUE;}
