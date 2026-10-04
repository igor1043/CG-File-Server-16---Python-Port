#pragma once
#include <algorithm>
// Must match StadiumSelector: 600x560 card, separate 1000x230 keyboard.
struct SelectorLayout {
    bool keyboard;
    float card_x,card_y,card_scale,card_width,card_height;
    float keyboard_x,keyboard_y,keyboard_scale;
};
inline SelectorLayout selector_layout(float viewport_width,float viewport_height,LONG image_width,LONG image_height) {
    SelectorLayout layout={};
    layout.keyboard=image_width==1000 && image_height==790;
    layout.card_width=layout.keyboard ? 600.f : (float)image_width;
    layout.card_height=layout.keyboard ? 560.f : (float)image_height;
    layout.card_y=viewport_height*.04f;
    float available=viewport_height*.66f;
    if (layout.keyboard) {
        layout.keyboard_scale=(std::min)((std::min)(viewport_width*.88f/1000.f,viewport_height*.28f/230.f),1.35f);
        layout.keyboard_x=(viewport_width-1000.f*layout.keyboard_scale)/2.f;
        layout.keyboard_y=viewport_height-230.f*layout.keyboard_scale-viewport_height*.035f;
        available=(std::min)(available,layout.keyboard_y-layout.card_y-viewport_height*.03f);
    }
    layout.card_scale=(std::min)((std::min)(viewport_width*.64f/layout.card_width,available/layout.card_height),1.05f);
    layout.card_x=(viewport_width-layout.card_width*layout.card_scale)/2.f;
    return layout;
}
inline bool selector_hit(const SelectorLayout &layout,float x,float y,LONG &logical_x,LONG &logical_y) {
    if (layout.keyboard && x>=layout.keyboard_x && y>=layout.keyboard_y &&
        x<layout.keyboard_x+1000.f*layout.keyboard_scale && y<layout.keyboard_y+230.f*layout.keyboard_scale) {
        logical_x=(LONG)((x-layout.keyboard_x)/layout.keyboard_scale);
        logical_y=560+(LONG)((y-layout.keyboard_y)/layout.keyboard_scale);
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
