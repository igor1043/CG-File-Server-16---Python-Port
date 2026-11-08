#pragma once
#include <windows.h>
#include <dxgi.h>
void ultrawide_initialize(HMODULE owner,void (*logger)(const char *));
void ultrawide_present(IDXGISwapChain *swapchain);
void ultrawide_overlay(bool drawing);
void ultrawide_stop();
void ultrawide_cursor_position(POINT *position);
