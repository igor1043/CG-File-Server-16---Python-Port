// A hidden software-rendered window; no FIFA injection or real input hooks.
#define CGFS16_OVERLAY_LOG_FILE "cgfs16_overlay_test.log"
#include "../server16_py/d3d_overlay/cgfs16_overlay.cpp"
#include <cassert>
static SelectorShared shared={};
SelectorShared *g_selector=&shared;
LONG g_selector_draw_width=0,g_selector_draw_height=0;
void selector_initialize(void (*)(const char *)) {}
void selector_tick(HWND,float,float) {}
bool selector_visible() { return shared.visible!=0; }
int wmain(int argc,wchar_t **argv) {
    assert(argc==1 || argc==4 || argc==5);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    InitLog(); InitializeCriticalSection(&g_drawCs);
    HWND window=CreateWindowExW(0,L"STATIC",L"",WS_POPUP,0,0,1280,720,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
    assert(window);
    DXGI_SWAP_CHAIN_DESC description={};
    description.BufferDesc.Width=1280; description.BufferDesc.Height=720;
    description.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;
    description.BufferCount=1; description.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;
    description.OutputWindow=window; description.SampleDesc.Count=1; description.Windowed=TRUE;
    IDXGISwapChain *swap=nullptr; ID3D11Device *device=nullptr; ID3D11DeviceContext *context=nullptr;
    assert(SUCCEEDED(D3D11CreateDeviceAndSwapChain(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&description,&swap,&device,nullptr,&context)));
    D3D11_BUFFER_DESC vb={}; vb.ByteWidth=64; vb.BindFlags=D3D11_BIND_VERTEX_BUFFER;
    ID3D11Buffer *original=nullptr; assert(SUCCEEDED(device->CreateBuffer(&vb,nullptr,&original)));
    UINT stride=16,offset=0; context->IASetVertexBuffers(0,1,&original,&stride,&offset);
    D3D11_VIEWPORT viewport={0,0,1280,720,0,1}; context->RSSetViewports(1,&viewport);
    struct GuardedQuads {
        Vtx11 vertices[4];
        unsigned char guard[sizeof(Vtx11)*4];
    } guarded={};
    memset(guarded.guard,0xA5,sizeof(guarded.guard));
    int count=0;
    assert(PushQuad(guarded.vertices,count,0,0,20,20,1280,720,0xFFFFFFFF));
    assert(count==4);
    assert(!PushQuad(guarded.vertices,count,0,0,20,20,1280,720,0xFFFFFFFF));
    assert(count==4);
    for(unsigned char byte:guarded.guard) assert(byte==0xA5);

    OverlayShared loading={};
    g_data=&loading;
    wcscpy_s(loading.stadium_name,L"Maracana");
    wcscpy_s(loading.scoreboard_name,L"Caze TV");
    wcscpy_s(loading.movie_name,L"Caze TV");
    wcscpy_s(loading.narration_name,L"Vilani");
    if(argc==5)wcscpy_s(loading.narration_image_path,argv[4]);
    for(int mask=1;mask<16;++mask) {
        loading.visible=mask&1;
        loading.scoreboard_visible=mask&2;
        loading.movie_visible=mask&4;
        loading.narration_visible=mask&8;
        for(LONG progress:{0L,100L,5500L,10000L}) {
            loading.progress_x100=loading.scoreboard_progress_x100=loading.movie_progress_x100=loading.narration_progress_x100=progress;
            DrawOverlay11(swap,device,context);
            ID3D11Buffer *restored=nullptr;
            context->IAGetVertexBuffers(0,1,&restored,&stride,&offset);
            assert(restored==original && stride==16 && offset==0);
            restored->Release();
        }
    }
    if(argc==5) {
        assert(g_narrationPortraitSRV && g_narrationPortraitW==104 && g_narrationPortraitH==104);
        assert(!g_previewSRV); // Narrator photo cannot overwrite stadium/selector texture.
        loading.narration_image_path[0]=0;loading.narration_visible=1;
        DrawOverlay11(swap,device,context);
        assert(!g_narrationPortraitSRV);
    }
    D3D11_BUFFER_DESC overlayBuffer={}; g_vb->GetDesc(&overlayBuffer);
    assert(overlayBuffer.ByteWidth==sizeof(Vtx11)*kColoredVertexCapacity);
    g_data=nullptr;
    puts("All loading-card combinations and buffer boundary protection passed");
    if(argc>=4) {
    shared.visible=1; shared.render_ready=1; shared.width=600; shared.height=600;
    wcscpy_s(shared.image_path,argv[1]);
    DrawOverlay11(swap,device,context);
    assert(g_previewSRV && shared.visible);
    ID3D11Buffer *after=nullptr; context->IAGetVertexBuffers(0,1,&after,&stride,&offset);
    assert(after==original && stride==16 && offset==0); after->Release();
    assert(photo_fade(0)==0 && photo_fade(220)==1 && photo_fade(110)>.49f && photo_fade(110)<.51f);
    wcscpy_s(shared.image_path,argv[3]); shared.render_ready=2;
    DrawOverlay11(swap,device,context);
    assert(g_previousPhoto && shared.visible);
    g_photoFadeStarted=GetTickCount()-250;
    DrawOverlay11(swap,device,context);
    assert(!g_previousPhoto);
    wcscpy_s(shared.image_path,argv[2]); shared.render_ready=3; shared.width=1000; shared.height=830;
    DrawOverlay11(swap,device,context);
    assert(g_previewSRV && g_previewNatW==2000 && g_previewNatH==1660 && shared.visible);
    shared.render_ready=0;
    DrawOverlay11(swap,device,context);
    assert(shared.visible);
    context->IAGetVertexBuffers(0,1,&after,&stride,&offset);
    assert(after==original && stride==16 && offset==0); after->Release();
    wcscpy_s(shared.image_path,L"Z:\\nonexistent-selector-image.png"); shared.render_ready=2;
    DrawOverlay11(swap,device,context);
    assert(shared.visible && g_previewSRV); // Failed replacement retains the visible card.
    shared.render_ready=-5;
    DrawOverlay11(swap,device,context);
    assert(shared.visible && g_previewSRV);
    g_selectorTexture=false; g_imageRetryAt=0;
    shared.render_ready=5;
    DrawOverlay11(swap,device,context);
    assert(!shared.visible); // Initial failure still releases game input.
    context->IAGetVertexBuffers(0,1,&after,&stride,&offset);
    assert(after==original && stride==16 && offset==0); after->Release();
    puts("Photo crossfade, detached keyboard, state restoration and missing-image tests passed");
    }
    original->Release(); context->Release(); device->Release(); swap->Release(); DestroyWindow(window);
    puts("Software D3D11 render tests passed");
    return 0;
}
