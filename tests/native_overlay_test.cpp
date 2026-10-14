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
    assert(argc==1 || argc==2 || argc==4 || argc==5);
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
    wcscpy_s(loading.presentation_name,L"Carregando apresenta\u00e7\u00e3o");
    wcscpy_s(loading.presentation_detail,L"Entradas: prontas\nPirotecnia: pronta\nVAR: aguardando cena\nM\u00e1quinas de fuma\u00e7a: prontas");
    static_assert(sizeof(OverlayShared)==7208,"Python notification ABI");
    for(int mask=1;mask<32;++mask) {
        loading.visible=mask&1;
        loading.scoreboard_visible=mask&2;
        loading.movie_visible=mask&4;
        loading.narration_visible=mask&8;
        loading.presentation_visible=mask&16;
        for(LONG progress:{0L,100L,5500L,10000L}) {
            loading.progress_x100=loading.scoreboard_progress_x100=loading.movie_progress_x100=loading.narration_progress_x100=loading.presentation_progress_x100=progress;
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
    if(argc==2){
        ID3D11Texture2D *back=nullptr,*readable=nullptr;
        assert(SUCCEEDED(swap->GetBuffer(0,__uuidof(ID3D11Texture2D),(void**)&back)));
        ID3D11RenderTargetView *target=nullptr;assert(SUCCEEDED(device->CreateRenderTargetView(back,nullptr,&target)));
        const float background[4]={.035f,.09f,.12f,1};context->ClearRenderTargetView(target,background);target->Release();
        g_data=&loading;loading.visible=loading.narration_visible=loading.presentation_visible=1;
        loading.scoreboard_visible=loading.movie_visible=0;
        loading.progress_x100=7500;loading.narration_progress_x100=10000;loading.presentation_progress_x100=7500;
        wcscpy_s(loading.presentation_detail,L"Entradas: pronto na cena 3D\nPirotecnia: pronto na cena 3D\nVAR: carregando cena 3D\nM\u00e1quinas de fuma\u00e7a: aguardando cena 3D");
        DrawOverlay11(swap,device,context);g_data=nullptr;
        D3D11_TEXTURE2D_DESC desc{};back->GetDesc(&desc);desc.Usage=D3D11_USAGE_STAGING;
        desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;desc.MiscFlags=0;
        assert(SUCCEEDED(device->CreateTexture2D(&desc,nullptr,&readable)));
        context->CopyResource(readable,back);back->Release();
        D3D11_MAPPED_SUBRESOURCE pixels{};assert(SUCCEEDED(context->Map(readable,0,D3D11_MAP_READ,0,&pixels)));
        IWICImagingFactory *factory=nullptr;IWICStream *stream=nullptr;IWICBitmapEncoder *encoder=nullptr;IWICBitmapFrameEncode *frame=nullptr;
        assert(SUCCEEDED(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&factory))));
        assert(SUCCEEDED(factory->CreateStream(&stream)));assert(SUCCEEDED(stream->InitializeFromFilename(argv[1],GENERIC_WRITE)));
        assert(SUCCEEDED(factory->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder)));
        assert(SUCCEEDED(encoder->Initialize(stream,WICBitmapEncoderNoCache)));assert(SUCCEEDED(encoder->CreateNewFrame(&frame,nullptr)));
        assert(SUCCEEDED(frame->Initialize(nullptr)));assert(SUCCEEDED(frame->SetSize(desc.Width,desc.Height)));
        WICPixelFormatGUID format=GUID_WICPixelFormat32bppRGBA;assert(SUCCEEDED(frame->SetPixelFormat(&format)));
        IWICBitmap *bitmap=nullptr;IWICFormatConverter *converter=nullptr;
        assert(SUCCEEDED(factory->CreateBitmapFromMemory(desc.Width,desc.Height,GUID_WICPixelFormat32bppRGBA,
            pixels.RowPitch,pixels.RowPitch*desc.Height,(BYTE*)pixels.pData,&bitmap)));
        assert(SUCCEEDED(factory->CreateFormatConverter(&converter)));
        assert(SUCCEEDED(converter->Initialize(bitmap,format,WICBitmapDitherTypeNone,nullptr,0,WICBitmapPaletteTypeCustom)));
        assert(SUCCEEDED(frame->WriteSource(converter,nullptr)));converter->Release();bitmap->Release();
        assert(SUCCEEDED(frame->Commit()));assert(SUCCEEDED(encoder->Commit()));
        frame->Release();encoder->Release();stream->Release();factory->Release();context->Unmap(readable,0);readable->Release();
        puts("Native loading notification image exported");
    }
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
