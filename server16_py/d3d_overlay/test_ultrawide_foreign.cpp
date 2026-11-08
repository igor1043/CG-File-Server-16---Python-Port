#include <d3d11.h>
static volatile LONG calls;
extern "C" __declspec(dllexport) void foreign_ui_draw(ID3D11DeviceContext *context) {
    context->Draw(3,0);
    // Keep this call site in a different DLL, like the club browser renderer.
    InterlockedIncrement(&calls);
}
