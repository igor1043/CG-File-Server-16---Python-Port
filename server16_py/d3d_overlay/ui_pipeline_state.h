#pragma once
#include <d3d11_1.h>

namespace clubgfx {
// The UI owns a complete D3D11 state object. Restoring the game's state does
// not replay individual IA bindings through animation/material interception.
struct UiPipelineState {
 ID3D11Device* device=nullptr;
 ID3D11DeviceContext1* context=nullptr;
 ID3DDeviceContextState* ui=nullptr,*previous=nullptr;
 unsigned enters=0,restores=0,unsupported=0;
 HRESULT error=S_OK;
 bool active=false;
 void leave(){
  if(!active)return;
  // Drop UI bindings while its own state is active; never retain a swap-chain
  // RTV/SRV across ResizeBuffers in windowed mode.
  context->ClearState();
  context->SwapDeviceContextState(previous,nullptr);
  previous->Release();previous=nullptr;active=false;++restores;
 }
 void clear(){
  leave();if(ui)ui->Release();if(context)context->Release();if(device)device->Release();
  ui=nullptr;context=nullptr;device=nullptr;
 }
 bool enter(ID3D11DeviceContext* candidate){
  if(active||!candidate||candidate->GetType()!=D3D11_DEVICE_CONTEXT_IMMEDIATE)return false;
  ID3D11Device* owner=nullptr;candidate->GetDevice(&owner);if(!owner)return false;
  if(owner!=device){clear();device=owner;owner=nullptr;}
  if(owner)owner->Release();
  if(!context){error=candidate->QueryInterface(__uuidof(ID3D11DeviceContext1),(void**)&context);if(FAILED(error)){++unsupported;return false;}}
  if(!ui){
   ID3D11Device1* version=nullptr;error=device->QueryInterface(__uuidof(ID3D11Device1),(void**)&version);
   if(FAILED(error)){++unsupported;return false;}
   D3D_FEATURE_LEVEL feature=device->GetFeatureLevel(),selected{};
   UINT flags=(device->GetCreationFlags()&D3D11_CREATE_DEVICE_SINGLETHREADED)?D3D11_1_CREATE_DEVICE_CONTEXT_STATE_SINGLETHREADED:0;
   error=version->CreateDeviceContextState(flags,&feature,1,D3D11_SDK_VERSION,__uuidof(ID3D11Device1),&selected,&ui);
   version->Release();if(FAILED(error)){++unsupported;return false;}
  }
  context->SwapDeviceContextState(ui,&previous);
  if(!previous){++unsupported;return false;}
  active=true;++enters;return true;
 }
};
}
