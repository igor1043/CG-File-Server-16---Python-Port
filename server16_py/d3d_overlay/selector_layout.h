#pragma once
#include <algorithm>
constexpr float kPanelZoom = 1.5f;
constexpr float kLoadingZoom = 1.f;
// Must match StadiumSelector: 600x600 card, separate 1000x230 keyboard.
struct SelectorLayout {
    bool keyboard;
    float card_x,card_y,card_scale,card_width,card_height;
    float keyboard_x,keyboard_y,keyboard_scale;
};
inline SelectorLayout selector_layout(float viewport_width,float viewport_height,LONG image_width,LONG image_height) {
    SelectorLayout layout={};
    layout.keyboard=image_width==1000 && image_height==830;
    layout.card_width=layout.keyboard ? 600.f : (float)image_width;
    layout.card_height=layout.keyboard ? 600.f : (float)image_height;
    layout.card_y=viewport_height*.04f;
    float available=viewport_height*.66f;
    if (layout.keyboard) {
        layout.keyboard_scale=(std::min)((std::min)(viewport_width*.88f/1000.f,viewport_height*.28f/230.f),1.35f);
        layout.keyboard_x=(viewport_width-1000.f*layout.keyboard_scale)/2.f;
        layout.keyboard_y=viewport_height-230.f*layout.keyboard_scale-viewport_height*.035f;
        available=(std::min)(available,layout.keyboard_y-layout.card_y-viewport_height*.03f);
    }
    layout.card_scale=(std::min)((std::min)(viewport_width*.64f/layout.card_width,available/layout.card_height),1.05f);
    if (image_height != 440) layout.card_scale *= .6f;
    // Grow the existing on-screen layout, not its logical input coordinates.
    // The detached keyboard shares this zoom but may shrink to fit the viewport.
    if (layout.keyboard) {
        layout.keyboard_scale=(std::min)(layout.keyboard_scale*kPanelZoom,viewport_width*.96f/1000.f);
        layout.keyboard_x=(viewport_width-1000.f*layout.keyboard_scale)/2.f;
        layout.keyboard_y=viewport_height-230.f*layout.keyboard_scale-viewport_height*.035f;
    }
    float bottom=layout.keyboard ? layout.keyboard_y-viewport_height*.03f : viewport_height*.965f;
    float fit=(std::min)(viewport_width*.96f/layout.card_width,(bottom-layout.card_y)/layout.card_height);
    layout.card_scale=(std::max)(0.f,(std::min)(layout.card_scale*kPanelZoom,fit));
    layout.card_x=(viewport_width-layout.card_width*layout.card_scale)/2.f;
    return layout;
}

struct LoadingLayout {
    float x,y,scale;
};
inline LoadingLayout loading_layout(float width,float height,float panel_width,float stack_height) {
    const float margin=16.f;
    float fit=(std::min)((width-margin*2.f)/panel_width,(height-margin*2.f)/stack_height);
    float scale=(std::max)(0.f,(std::min)(kLoadingZoom,fit));
    return {width-panel_width*scale-margin,margin,scale};
}
inline bool selector_hit(const SelectorLayout &layout,float x,float y,LONG &logical_x,LONG &logical_y) {
    if (layout.keyboard && x>=layout.keyboard_x && y>=layout.keyboard_y &&
        x<layout.keyboard_x+1000.f*layout.keyboard_scale && y<layout.keyboard_y+230.f*layout.keyboard_scale) {
        logical_x=(LONG)((x-layout.keyboard_x)/layout.keyboard_scale);
        logical_y=600+(LONG)((y-layout.keyboard_y)/layout.keyboard_scale);
        return true;
    }
    if (x>=layout.card_x && y>=layout.card_y && x<layout.card_x+layout.card_width*layout.card_scale &&
        y<layout.card_y+layout.card_height*layout.card_scale) {
        logical_x=(LONG)((x-layout.card_x)/layout.card_scale);
        logical_y=(LONG)((y-layout.card_y)/layout.card_scale);
        return true;
    }
    return false;
}
