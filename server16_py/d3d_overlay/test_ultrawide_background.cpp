#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "ultrawide_background.h"
#include <assert.h>
#include <algorithm>

struct Picture {
    UINT width,height;
    DXGI_FORMAT format,typeless,gamma;
    std::vector<unsigned char> pixels;
};

static Picture read_picture(const wchar_t *path) {
    FILE *file=nullptr;
    assert(!_wfopen_s(&file,path,L"rb"));
    assert(!_fseeki64(file,0,SEEK_END));
    size_t length=size_t(_ftelli64(file));
    rewind(file);
    std::vector<unsigned char> data(length);
    assert(fread(data.data(),1,length,file)==length);
    fclose(file);
    // Extract the fixture independently from the production BIG reader.
    const unsigned char magic[]={'D','D','S',' '};
    auto start=std::search(data.begin(),data.end(),magic,magic+4);
    assert(start!=data.end()&&data.end()-start>=128);
    auto word=[&](size_t at){UINT value;memcpy(&value,&start[at],4);return value;};
    Picture image={};
    image.width=word(16);image.height=word(12);
    bool bc3=!memcmp(&start[84],"DXT5",4);
    assert(bc3||!memcmp(&start[84],"DXT3",4));
    image.format=bc3?DXGI_FORMAT_BC3_UNORM:DXGI_FORMAT_BC2_UNORM;
    image.typeless=bc3?DXGI_FORMAT_BC3_TYPELESS:DXGI_FORMAT_BC2_TYPELESS;
    image.gamma=bc3?DXGI_FORMAT_BC3_UNORM_SRGB:DXGI_FORMAT_BC2_UNORM_SRGB;
    size_t bytes=size_t((image.width+3)/4)*((image.height+3)/4)*16;
    assert(size_t(data.end()-start)>=128+bytes);
    image.pixels.assign(start+128,start+128+bytes);
    return image;
}

static ID3D11ShaderResourceView *native_image(
    ID3D11Device *device,Picture image,bool gamma,bool different
) {
    if(different)image.pixels[image.pixels.size()/2]^=0xff;
    D3D11_TEXTURE2D_DESC desc={};
    desc.Width=image.width;desc.Height=image.height;
    desc.MipLevels=desc.ArraySize=desc.SampleDesc.Count=1;
    desc.Format=image.typeless;desc.Usage=D3D11_USAGE_IMMUTABLE;
    desc.BindFlags=D3D11_BIND_SHADER_RESOURCE;
    D3D11_SUBRESOURCE_DATA data={image.pixels.data(),((image.width+3)/4)*16,0};
    ID3D11Texture2D *texture=nullptr;
    assert(SUCCEEDED(device->CreateTexture2D(&desc,&data,&texture)));
    D3D11_SHADER_RESOURCE_VIEW_DESC view={};
    view.Format=gamma?image.gamma:image.format;
    view.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;view.Texture2D.MipLevels=1;
    ID3D11ShaderResourceView *result=nullptr;
    assert(SUCCEEDED(device->CreateShaderResourceView(texture,&view,&result)));
    texture->Release();
    return result;
}

static void verify_pixels(
    ID3D11Device *device,ID3D11DeviceContext *ctx,
    ID3D11ShaderResourceView *view,const Picture &expected,bool gamma
) {
    D3D11_SHADER_RESOURCE_VIEW_DESC srv={};view->GetDesc(&srv);
    assert(srv.Format==(gamma?expected.gamma:expected.format));
    ID3D11Resource *resource=nullptr;view->GetResource(&resource);
    ID3D11Texture2D *texture=nullptr;
    assert(SUCCEEDED(resource->QueryInterface(__uuidof(ID3D11Texture2D),(void**)&texture)));
    resource->Release();
    D3D11_TEXTURE2D_DESC desc={};texture->GetDesc(&desc);
    assert(desc.Width==expected.width&&desc.Height==expected.height);
    desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
    ID3D11Texture2D *copy=nullptr;
    assert(SUCCEEDED(device->CreateTexture2D(&desc,nullptr,&copy)));
    ctx->CopyResource(copy,texture);
    D3D11_MAPPED_SUBRESOURCE map={};
    assert(SUCCEEDED(ctx->Map(copy,0,D3D11_MAP_READ,0,&map)));
    const size_t row=((expected.width+3)/4)*16;
    for(size_t y=0;y<(expected.height+3)/4;++y)
        assert(!memcmp((unsigned char*)map.pData+y*map.RowPitch,expected.pixels.data()+y*row,row));
    ctx->Unmap(copy,0);
    copy->Release();texture->Release();
}

int wmain(int argc,wchar_t **argv) {
    assert(argc==7);
    ID3D11Device *device=nullptr;ID3D11DeviceContext *ctx=nullptr;
    assert(SUCCEEDED(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,D3D11_SDK_VERSION,&device,nullptr,&ctx)));
    ultrawide::Backgrounds images;
    for(int pair=0;pair<3;++pair)
        assert(images.initialize(argv[1+pair*2],argv[2+pair*2],static_cast<ultrawide::Artwork>(pair+1)));
    for(int pair=0;pair<3;++pair) {
        const auto kind=static_cast<ultrawide::Artwork>(pair+1);
        const Picture pictures[]={read_picture(argv[1+pair*2]),read_picture(argv[2+pair*2])};
        assert(pictures[0].pixels!=pictures[1].pixels);
        for(bool gamma:{false,true})for(int source=0;source<2;++source) {
            auto *original=native_image(device,pictures[source],gamma,false);
            for(bool wide:{false,true,false,true}) {
                ctx->PSSetShaderResources(0,1,&original);
                ID3D11ShaderResourceView *old=nullptr;
                assert(images.select_artwork(ctx,wide,old)==kind&&old==original);
                ID3D11ShaderResourceView *selected=nullptr;
                ctx->PSGetShaderResources(0,1,&selected);
                verify_pixels(device,ctx,selected,pictures[wide?1:0],gamma);
                selected->Release();
                ctx->PSSetShaderResources(0,1,&old);old->Release();
            }
            ID3D11ShaderResourceView *none=nullptr,*old=nullptr;
            ctx->PSSetShaderResources(0,1,&none);ctx->PSSetShaderResources(2,1,&original);
            assert(images.select_artwork(ctx,true,old)==ultrawide::Artwork::None&&!old);
            ctx->PSSetShaderResources(2,1,&none);original->Release();
        }
        auto *other=native_image(device,pictures[0],false,true);
        ctx->PSSetShaderResources(0,1,&other);
        ID3D11ShaderResourceView *old=nullptr,*none=nullptr;
        assert(images.select_artwork(ctx,true,old)==ultrawide::Artwork::None&&!old);
        ctx->PSSetShaderResources(0,1,&none);other->Release();
    }
    images.clear();ctx->ClearState();ctx->Release();device->Release();
    puts("PASS: all six actual assets, exact GPU pixels in both directions, BC2/BC3 and sRGB, stale bindings and unrelated textures excluded.");
}
