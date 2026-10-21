// Layout-only tests: no game process, injection or input hooks.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cassert>
#include <cmath>
#include <cstdio>
#include "../server16_py/d3d_overlay/selector_layout.h"

int main() {
    // Uncapped layouts preserve the zoom exactly. Taller cards are checked
    // below across viewports, where fitting can reduce their scale.
    for (LONG height : {390L,435L,440L,460L,545L,600L,650L}) {
        auto layout=selector_layout(1920.f,1080.f,600,height);
        float oldScale=1.05f*(height==440 ? 1.f : .6f);
        assert(std::abs(layout.card_scale-oldScale*1.5f)<.0001f);
        LONG x=0,y=0;
        assert(selector_hit(layout,layout.card_x+575.f*layout.card_scale,
                            layout.card_y+(height-20.f)*layout.card_scale,x,y));
        assert(std::abs(x-575)<=1 && std::abs(y-(height-20))<=1);
    }
    auto keyboard=selector_layout(3440.f,1440.f,1000,830);
    assert(std::abs(keyboard.keyboard_scale-1.35f*1.5f)<.0001f);
    assert(keyboard.card_y+600.f*keyboard.card_scale<keyboard.keyboard_y);
    for (auto viewport : {std::pair<float,float>(640,480),{800,600},{1280,720},
                           {1920,1080},{3440,1440},{720,1280}}) {
        for (LONG height : {390L,435L,440L,460L,545L,600L,650L,680L,830L}) {
            auto layout=selector_layout(viewport.first,viewport.second,height==830?1000:600,height);
            assert(layout.card_scale>0);
            assert(layout.card_x>=0 && layout.card_y>=0);
            assert(layout.card_x+layout.card_width*layout.card_scale<=viewport.first);
            assert(layout.card_y+layout.card_height*layout.card_scale<viewport.second);
            LONG x=0,y=0;
            assert(selector_hit(layout,layout.card_x+200*layout.card_scale,
                                layout.card_y+200*layout.card_scale,x,y));
            assert(std::abs(x-200)<=1 && std::abs(y-200)<=1);
            if (layout.keyboard) {
                assert(layout.keyboard_x>=0);
                assert(layout.card_y+600*layout.card_scale<layout.keyboard_y);
                assert(layout.keyboard_x+1000*layout.keyboard_scale<=viewport.first);
                assert(layout.keyboard_y+230*layout.keyboard_scale<viewport.second);
                assert(selector_hit(layout,layout.keyboard_x+900*layout.keyboard_scale,
                                    layout.keyboard_y+190*layout.keyboard_scale,x,y));
                assert(std::abs(x-900)<=1 && std::abs(y-790)<=1);
            }
        }
        for (float width : {280.f,420.f}) {
            for (float stack : {66.f,128.f,356.f}) {
                auto loading=loading_layout(viewport.first,viewport.second,width,stack);
                assert(loading.scale>0 && loading.scale<=1.f);
                assert(loading.x>=16.f-.001f);
                assert(loading.x+width*loading.scale<=viewport.first-16.f+.001f);
                assert(loading.y+stack*loading.scale<=viewport.second-16.f+.001f);
            }
        }
    }
    auto notice=loading_layout(1920.f,1080.f,420.f,356.f);
    assert(notice.scale==1.f);
    assert(notice.x==1920.f-420.f-16.f);
    puts("1.5x panels/keyboard, original-size notices, viewport bounds and mouse mapping passed.");
}
