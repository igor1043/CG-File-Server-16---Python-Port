#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "ultrawide_bridge.h"
#include "ultrawide_math.h"
#include "ui_pipeline_state.h"
#include <d3d11.h>
#include <d3dcompiler.h>
#include <assert.h>
#include <stdio.h>
#include <vector>
extern "C" void ultrawide_test_attach(IDXGISwapChain*,ID3D11DeviceContext*,bool);
extern "C" void ultrawide_test_release();
extern "C" void ultrawide_test_backgrounds(const wchar_t*,const wchar_t*);
extern "C" bool ultrawide_test_pointer(HWND,POINT*,bool);
extern "C" LRESULT ultrawide_test_message(HWND,UINT,WPARAM,LPARAM,WNDPROC);
static POINT received;
static LRESULT CALLBACK capture_message(HWND,UINT,WPARAM,LPARAM lp){received={SHORT(LOWORD(lp)),SHORT(HIWORD(lp))};return 123;}
#define CHECK(x) do{if(FAILED(x)){fprintf(stderr,"FAIL %s line %d\n",#x,__LINE__);return 1;}}while(0)
static const char *shader=R"(
float4 vs(uint id:SV_VertexID):SV_Position {return float4(id==2?3:-1,id==1?3:-1,0,1);}
float4 ps():SV_Target {return float4(1,1,1,1);}
)";
int wmain(int argc,wchar_t **argv) {
    assert(ultrawide::ui_region(1920,1080).scale==1);
    assert(ultrawide::ui_region(1024,768).scale==1);
    assert(fabsf(ultrawide::ui_region(2560,1080).x-320)<.01f);
    assert(fabsf(ultrawide::ui_region(5120,1440).x-1280)<.01f);
    for(auto size:std::vector<std::pair<float,float>>{{1920,1080},{2560,1080},{2560,1061},{3440,1440},{5120,1440}}) {
        auto region=ultrawide::ui_region(size.first,size.second);
        for(int i=0;i<=100;++i){float native=size.first*i/100.f;float physical=region.x+native*region.scale;
            assert(fabsf(ultrawide::ui_pointer_x(physical,size.first,size.first,size.second)-native)<.002f);}
    }
    std::vector<uint8_t> bytes(256);memcpy(bytes.data()+24,ultrawide::anchor,sizeof(ultrawide::anchor));size_t at=0;
    assert(ultrawide::find_anchor(bytes.data(),bytes.size(),at)==1&&at==24);
    memcpy(bytes.data()+128,ultrawide::anchor,sizeof(ultrawide::anchor));assert(ultrawide::find_anchor(bytes.data(),bytes.size(),at)==2);
    bytes[24]=0;bytes[128]=0;assert(!ultrawide::find_anchor(bytes.data(),bytes.size(),at));
    HWND window=CreateWindowExW(0,L"STATIC",L"ultrawide test",WS_POPUP,0,0,256,108,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
    DXGI_SWAP_CHAIN_DESC desc={};desc.BufferCount=1;desc.BufferDesc.Width=256;desc.BufferDesc.Height=108;
    desc.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;desc.OutputWindow=window;desc.SampleDesc.Count=1;desc.Windowed=TRUE;
    ID3D11Device *device=nullptr;ID3D11DeviceContext *ctx=nullptr;IDXGISwapChain *sc=nullptr;
    CHECK(D3D11CreateDeviceAndSwapChain(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&desc,&sc,&device,nullptr,&ctx));
    ID3DBlob *vsb=nullptr,*psb=nullptr;CHECK(D3DCompile(shader,strlen(shader),nullptr,nullptr,nullptr,"vs","vs_4_0",0,0,&vsb,nullptr));
    CHECK(D3DCompile(shader,strlen(shader),nullptr,nullptr,nullptr,"ps","ps_4_0",0,0,&psb,nullptr));
    ID3D11VertexShader *vs=nullptr;ID3D11PixelShader *ps=nullptr;CHECK(device->CreateVertexShader(vsb->GetBufferPointer(),vsb->GetBufferSize(),nullptr,&vs));
    CHECK(device->CreatePixelShader(psb->GetBufferPointer(),psb->GetBufferSize(),nullptr,&ps));vsb->Release();psb->Release();
    ID3D11Texture2D *bb=nullptr;CHECK(sc->GetBuffer(0,__uuidof(ID3D11Texture2D),(void**)&bb));
    ID3D11RenderTargetView *rt=nullptr;CHECK(device->CreateRenderTargetView(bb,nullptr,&rt));
    D3D11_TEXTURE2D_DESC td={};bb->GetDesc(&td);td.Usage=D3D11_USAGE_STAGING;td.CPUAccessFlags=D3D11_CPU_ACCESS_READ;td.BindFlags=0;td.MiscFlags=0;
    ID3D11Texture2D *read=nullptr;CHECK(device->CreateTexture2D(&td,nullptr,&read));
    D3D11_RASTERIZER_DESC rsd={};rsd.FillMode=D3D11_FILL_SOLID;rsd.CullMode=D3D11_CULL_NONE;rsd.DepthClipEnable=TRUE;rsd.ScissorEnable=TRUE;
    ID3D11RasterizerState *rs=nullptr;CHECK(device->CreateRasterizerState(&rsd,&rs));ctx->RSSetState(rs);
    ctx->VSSetShader(vs,nullptr,0);ctx->PSSetShader(ps,nullptr,0);ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    const float red[]={1,0,0,1};D3D11_VIEWPORT vp={0,0,256,108,0,1};D3D11_RECT rect={0,0,256,108};
    for(int test=0;test<5;++test) {
        ultrawide_test_attach(sc,ctx,test!=1);ctx->OMSetRenderTargets(1,&rt,nullptr);ctx->RSSetViewports(1,&vp);ctx->RSSetScissorRects(1,&rect);
        ctx->ClearRenderTargetView(rt,red);
        // First full-screen draw is the native scene copy, and must stay wide.
        ctx->Draw(3,0);ctx->CopyResource(read,bb);
        D3D11_MAPPED_SUBRESOURCE map={};CHECK(ctx->Map(read,0,D3D11_MAP_READ,0,&map));
        auto pixel=(unsigned char*)map.pData+54*map.RowPitch;assert(pixel[0]==255&&pixel[1]==255&&pixel[255*4+1]==255);ctx->Unmap(read,0);
        ctx->ClearRenderTargetView(rt,red);
        if(test==2)ultrawide_overlay(true);
        if(test==3){D3D11_RECT half={128,0,256,108};ctx->RSSetScissorRects(1,&half);}
        if(test==4){
            clubgfx::UiPipelineState state;
            ultrawide_overlay(true);assert(state.enter(ctx));state.leave();state.clear();ultrawide_overlay(false);
        }
        if(test==4)ctx->DrawInstanced(3,1,0,0);else ctx->Draw(3,0);
        ultrawide_overlay(false);
        ctx->CopyResource(read,bb);CHECK(ctx->Map(read,0,D3D11_MAP_READ,0,&map));pixel=(unsigned char*)map.pData+54*map.RowPitch;
        if(test==1||test==2){assert(pixel[1]==255&&pixel[255*4+1]==255);}
        else {assert(pixel[1]==0&&pixel[255*4+1]==0&&pixel[200*4+1]==255);if(test==3)assert(pixel[64*4+1]==0);else assert(pixel[64*4+1]==255);}
        ctx->Unmap(read,0);
        D3D11_VIEWPORT after={};UINT n=1;ctx->RSGetViewports(&n,&after);assert(!memcmp(&vp,&after,sizeof(vp)));
        D3D11_RECT afterRect={};n=1;ctx->RSGetScissorRects(&n,&afterRect);assert(afterRect.left==(test==3?128:0)&&afterRect.right==256);
    }
    // On/off changes the scene, but the native mouse always targets the same
    // centred 16:9 canvas. Check messages and polling without moving a cursor.
    for(bool active:{false,true}){
        ultrawide_test_attach(sc,ctx,active);
        POINT point={32,54};assert(ultrawide_test_pointer(window,&point,false));assert(point.x==0&&point.y==54);
        POINT origin={};assert(ClientToScreen(window,&origin));point={origin.x+224,origin.y+54};
        assert(ultrawide_test_pointer(window,&point,true));assert(point.x==origin.x+256&&point.y==origin.y+54);
        assert(ultrawide_test_message(window,WM_LBUTTONDOWN,0,MAKELPARAM(32,54),capture_message)==123);
        assert(received.x==0&&received.y==54);
        ultrawide_test_message(window,WM_MOUSEWHEEL,0,MAKELPARAM(origin.x+224,origin.y+54),capture_message);
        assert(received.x==origin.x+256&&received.y==origin.y+54);
    }
    // A pre-centred viewport must not be squeezed again.
    ultrawide_test_attach(sc,ctx,true);ctx->OMSetRenderTargets(1,&rt,nullptr);ctx->RSSetViewports(1,&vp);ctx->RSSetScissorRects(1,&rect);ctx->Draw(3,0);
    D3D11_VIEWPORT centred={32,0,192,108,0,1};D3D11_RECT centredRect={32,0,224,108};
    ctx->RSSetViewports(1,&centred);ctx->RSSetScissorRects(1,&centredRect);ctx->ClearRenderTargetView(rt,red);ctx->Draw(3,0);
    ctx->CopyResource(read,bb);D3D11_MAPPED_SUBRESOURCE mapped={};CHECK(ctx->Map(read,0,D3D11_MAP_READ,0,&mapped));
    auto row=(unsigned char*)mapped.pData+54*mapped.RowPitch;assert(row[20*4+1]==0&&row[40*4+1]==255&&row[210*4+1]==255);ctx->Unmap(read,0);
    // Independent mod renderers already centre their geometry and mouse; they
    // must not inherit the native frontend's extra viewport conversion.
    HMODULE foreign=LoadLibraryW(L"build\\test_ultrawide_foreign.dll");assert(foreign);
    auto foreignDraw=(void(*)(ID3D11DeviceContext*))GetProcAddress(foreign,"foreign_ui_draw");assert(foreignDraw);
    ctx->RSSetViewports(1,&vp);ctx->RSSetScissorRects(1,&rect);ctx->ClearRenderTargetView(rt,red);foreignDraw(ctx);
    ctx->CopyResource(read,bb);CHECK(ctx->Map(read,0,D3D11_MAP_READ,0,&mapped));row=(unsigned char*)mapped.pData+54*mapped.RowPitch;
    assert(row[1]==255&&row[255*4+1]==255);ctx->Unmap(read,0);FreeLibrary(foreign);
    if(argc==3) {
        ultrawide_test_backgrounds(argv[1],argv[2]);
        FILE *file=nullptr;assert(!_wfopen_s(&file,argv[1],L"rb"));unsigned char header[128];assert(fread(header,1,128,file)==128);
        UINT w,h;memcpy(&w,header+16,4);memcpy(&h,header+12,4);std::vector<unsigned char> pixels(size_t((w+3)/4)*((h+3)/4)*16);
        assert(fread(pixels.data(),1,pixels.size(),file)==pixels.size());fclose(file);
        D3D11_TEXTURE2D_DESC bg={};bg.Width=w;bg.Height=h;bg.MipLevels=bg.ArraySize=bg.SampleDesc.Count=1;
        bg.Format=DXGI_FORMAT_BC2_UNORM;bg.BindFlags=D3D11_BIND_SHADER_RESOURCE;bg.Usage=D3D11_USAGE_IMMUTABLE;
        D3D11_SUBRESOURCE_DATA data={pixels.data(),((w+3)/4)*16,0};ID3D11Texture2D *texture=nullptr;
        CHECK(device->CreateTexture2D(&bg,&data,&texture));ID3D11ShaderResourceView *image=nullptr;
        CHECK(device->CreateShaderResourceView(texture,nullptr,&image));texture->Release();
        ultrawide_test_attach(sc,ctx,true);ctx->OMSetRenderTargets(1,&rt,nullptr);ctx->RSSetViewports(1,&vp);ctx->RSSetScissorRects(1,&rect);
        ctx->Draw(3,0);ctx->ClearRenderTargetView(rt,red);ctx->PSSetShaderResources(0,1,&image);ctx->Draw(3,0);
        ctx->CopyResource(read,bb);D3D11_MAPPED_SUBRESOURCE map={};CHECK(ctx->Map(read,0,D3D11_MAP_READ,0,&map));
        auto pixel=(unsigned char*)map.pData+54*map.RowPitch;
        // Same draw/shader and viewport: the identified backdrop fills both
        // outer edges, while the ordinary UI draws above stayed centred.
        assert(pixel[1]==255&&pixel[255*4+1]==255);ctx->Unmap(read,0);
        ID3D11ShaderResourceView *restored=nullptr;ctx->PSGetShaderResources(0,1,&restored);assert(restored==image);restored->Release();
        ID3D11ShaderResourceView *none=nullptr;ctx->PSSetShaderResources(0,1,&none);
        ctx->PSSetShaderResources(3,1,&image);ctx->ClearRenderTargetView(rt,red);ctx->Draw(3,0);
        ctx->CopyResource(read,bb);CHECK(ctx->Map(read,0,D3D11_MAP_READ,0,&map));pixel=(unsigned char*)map.pData+54*map.RowPitch;
        assert(pixel[1]==0&&pixel[64*4+1]==255&&pixel[255*4+1]==0);ctx->Unmap(read,0);
        ctx->PSSetShaderResources(3,1,&none);image->Release();
    }
    ultrawide_test_release();ctx->OMSetRenderTargets(0,nullptr,nullptr);rt->Release();bb->Release();read->Release();
    // No retained backbuffer references are allowed to break resize/fullscreen.
    CHECK(sc->ResizeBuffers(1,320,108,DXGI_FORMAT_UNKNOWN,0));
    rs->Release();vs->Release();ps->Release();ctx->Release();device->Release();sc->Release();DestroyWindow(window);
    puts("PASS: native aspect math, unique anchor, real D3D11 WARP draws, centred UI, scissors, off switch, overlay exclusion, exact state restoration and resize.");
}
