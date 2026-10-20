#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <initializer_list>
#include "../camera_channel.h"
static uintptr_t image,bc;
static volatile LONG started=0,stopping=0,fix=0;
using Call=void(__fastcall*)(void*,void*);
static Call generator;
using GetFrame=void*(__fastcall*)(void*,double);
static GetFrame post;
static CameraChannel* channel;
static volatile LONG* headEnabled;
static SRWLOCK lock=SRWLOCK_INIT;
struct Source {float data[28]{};ULONGLONG tick=0;int selected=-1,phase=0;bool valid=false;};
static Source source{};
extern "C" {__declspec(dllexport) struct AnchorPublic {
    uint32_t version=1,size=sizeof(AnchorPublic);
    int32_t enabled=0,valid=0,selected=-1,phase=0;
    int64_t frames=0,applied=0;
    float positionError=0,targetError=0;
    float source[28]{},before[28]{},after[28]{};
    uint64_t behavior=0,output=0;
} AnchorStatus{};}
static bool read(uintptr_t a,void* out,size_t n){
    if(a<0x10000||a>UINTPTR_MAX-n)return false;
    __try{std::memcpy(out,reinterpret_cast<void*>(a),n);return true;}__except(EXCEPTION_EXECUTE_HANDLER){return false;}
}
template<class T>static T get(uintptr_t a){T x{};read(a,&x,sizeof x);return x;}
static bool swap(uintptr_t slot,uintptr_t from,uintptr_t to){
    DWORD old=0;if(!VirtualProtect(reinterpret_cast<void*>(slot),8,PAGE_READWRITE,&old))return false;
    auto actual=InterlockedCompareExchangePointer(reinterpret_cast<void* volatile*>(slot),reinterpret_cast<void*>(to),reinterpret_cast<void*>(from));
    DWORD ignored=0;VirtualProtect(reinterpret_cast<void*>(slot),8,old,&ignored);return actual==reinterpret_cast<void*>(from);
}
static bool active(){return !stopping&&channel&&channel->version==4&&channel->owner&&channel->requested&&channel->enabled&&channel->mode==0&&
    static_cast<uint32_t>(GetTickCount()-channel->heartbeat)<1500&&headEnabled&&*headEnabled==1;}
static bool finitePose(const float* p){
    for(int i:{0,1,2,4,5,6,12,13,14,16,17})if(!std::isfinite(p[i]))return false;
    return std::fabs(p[0])<20000&&std::fabs(p[2])<20000&&p[1]>10&&p[1]<1000;
}
static float distance(const float* a,const float* b){
    const float x=a[0]-b[0],y=a[1]-b[1],z=a[2]-b[2];return std::sqrt(x*x+y*y+z*z);
}
static void __fastcall generatorHook(void* self,void* output){
    generator(self,output);
    Source s{};const auto behavior=reinterpret_cast<uintptr_t>(self);
    s.tick=GetTickCount64();s.selected=get<int>(behavior+0x9cc);s.phase=get<int>(behavior+0xaa4);
    s.valid=active()&&s.selected>=0&&s.selected<46&&(s.phase==2||s.phase==14||s.phase==15)&&
        read(reinterpret_cast<uintptr_t>(output),s.data,sizeof s.data)&&finitePose(s.data)&&s.data[14]==2.f&&std::fabs(distance(s.data,s.data+4)-1000.f)<1.f;
    AcquireSRWLockExclusive(&lock);source=s;ReleaseSRWLockExclusive(&lock);
}
static void* __fastcall postHook(void* self,double time){
    void* output=post(self,time);
    AcquireSRWLockShared(&lock);const auto s=source;ReleaseSRWLockShared(&lock);
    AnchorStatus.frames++;AnchorStatus.enabled=fix?1:0;
    AnchorStatus.valid=output&&s.valid&&active()&&GetTickCount64()-s.tick<50;
    AnchorStatus.selected=s.selected;AnchorStatus.phase=s.phase;
    AnchorStatus.behavior=reinterpret_cast<uintptr_t>(self);AnchorStatus.output=reinterpret_cast<uintptr_t>(output);
    if(!output)return output;
    const uintptr_t out=reinterpret_cast<uintptr_t>(output);
    float matrix[16]{};
    if(!read(out+0x30,matrix,sizeof matrix))return output;
    std::memcpy(AnchorStatus.source,s.data,sizeof s.data);
    std::memset(AnchorStatus.before,0,sizeof AnchorStatus.before);
    std::memcpy(AnchorStatus.before,matrix,sizeof matrix);
    std::memcpy(AnchorStatus.after,AnchorStatus.before,sizeof AnchorStatus.after);
    const float eye[]={matrix[12],matrix[13],-matrix[14]};
    AnchorStatus.positionError=distance(s.data,eye);
    AnchorStatus.targetError=static_cast<float>(GetTickCount64()-s.tick);
    // Observer first: no camera data is changed until this final transform is checked.
    return output;
}
extern "C" __declspec(dllexport) DWORD WINAPI Start(void*){
    if(started)return stopping?0:1;
    image=reinterpret_cast<uintptr_t>(GetModuleHandleW(nullptr));bc=reinterpret_cast<uintptr_t>(GetModuleHandleW(L"BCEnginezf.dll"));
    auto head=GetModuleHandleW(L"server16_head_ram_v12.dll");if(!head||!bc)return 0;
    auto status=GetProcAddress(head,"HeadRamStatus");if(!status)return 0;headEnabled=reinterpret_cast<volatile LONG*>(reinterpret_cast<uintptr_t>(status)+8);
    generator=reinterpret_cast<Call>(get<uintptr_t>(bc+0x1254f0));post=reinterpret_cast<GetFrame>(bc+0x3fd90);
    MEMORY_BASIC_INFORMATION mbi{};
    if(!VirtualQuery(reinterpret_cast<void*>(generator),&mbi,sizeof mbi)||mbi.AllocationBase!=head||get<uintptr_t>(bc+0x113318)!=reinterpret_cast<uintptr_t>(post))return 0;
    HANDLE map=OpenFileMappingW(FILE_MAP_READ,FALSE,CAMERA_MAPPING_NAME);if(!map)return 0;
    channel=static_cast<CameraChannel*>(MapViewOfFile(map,FILE_MAP_READ,0,0,sizeof(CameraChannel)));if(!channel)return 0;
    HMODULE pin=nullptr;if(!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCWSTR>(&image),&pin))return 0;
    if(!swap(bc+0x1254f0,reinterpret_cast<uintptr_t>(generator),reinterpret_cast<uintptr_t>(&generatorHook)))return 0;
    if(!swap(bc+0x113318,reinterpret_cast<uintptr_t>(post),reinterpret_cast<uintptr_t>(&postHook))){swap(bc+0x1254f0,reinterpret_cast<uintptr_t>(&generatorHook),reinterpret_cast<uintptr_t>(generator));return 0;}
    InterlockedExchange(&started,1);return 1;
}
extern "C" __declspec(dllexport) DWORD WINAPI Enable(void*){if(stopping)return 0;InterlockedExchange(&fix,1);return 1;}
extern "C" __declspec(dllexport) DWORD WINAPI Disable(void*){InterlockedExchange(&fix,0);return 1;}
extern "C" __declspec(dllexport) DWORD WINAPI Stop(void*){
    InterlockedExchange(&fix,0);InterlockedExchange(&stopping,1);
    const bool a=swap(bc+0x1254f0,reinterpret_cast<uintptr_t>(&generatorHook),reinterpret_cast<uintptr_t>(generator));
    const bool b=swap(bc+0x113318,reinterpret_cast<uintptr_t>(&postHook),reinterpret_cast<uintptr_t>(post));return a&&b?1:0;
}
BOOL WINAPI DllMain(HINSTANCE,DWORD,LPVOID){return TRUE;}
