"""Code-drawn Xbox glyphs; no external images or font-symbol dependency."""

PANEL_FUNCTION_KEYS = ('F3', 'F4', 'F5', 'F8', 'F9')


def panel_function_key(action):
    """Match native action slots; F6/F7 remain the cloth controls."""
    if not 1 <= action <= len(PANEL_FUNCTION_KEYS):
        raise ValueError('Unknown panel action')
    return PANEL_FUNCTION_KEYS[action - 1]


def controller_connected(selector):
    return bool(getattr(selector, 'controller_connected', False))


def footer_y(height):
    # Room above the hints and below their D-pad/button glyphs.
    return height-41


def xbox_button(draw, selector, x, y, button, radius=10):
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill='white', outline='#52616f', width=1)
    font = selector.font(13, True)
    draw.text((x, y), button, font=font, fill='#344651', anchor='mm')


def action_label(draw, selector, rect, label, key, button, color='#344651', size=15, show_icon=True):
    pad = controller_connected(selector)
    icon = pad and show_icon
    font = selector.font(size)
    caption = label if pad else f'{label} · {key}'
    width = draw.textlength(caption, font=font) + (27 if icon else 0)
    x = (rect[0]+rect[2]-width)/2
    y = (rect[1]+rect[3])/2
    if icon:
        xbox_button(draw, selector, x+10, y, button)
        x += 27
    draw.text((x, y-size*.65), caption, font=font, fill=color)


def navigation_hint(draw, selector, y, confirm='Confirmar', back='Voltar'):
    font = selector.font(12)
    muted = '#728397'
    if not controller_connected(selector):
        draw.text((24, y), f'Setas: selecionar / ajustar · Enter: {confirm.lower()}', font=font, fill=muted)
        return
    # A small D-pad glyph, followed by only the actions actually handled.
    draw.rounded_rectangle((24, y+2, 46, y+10), 2, fill=muted)
    draw.rounded_rectangle((31, y-5, 39, y+17), 2, fill=muted)
    draw.text((54, y-2), 'Selecionar / ajustar', font=font, fill=muted)
    xbox_button(draw, selector, 237, y+6, 'A', 9)
    draw.text((252, y-2), confirm, font=font, fill=muted)
    xbox_button(draw, selector, 398, y+6, 'B', 9)
    draw.text((413, y-2), back, font=font, fill=muted)
