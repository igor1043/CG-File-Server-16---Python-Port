from __future__ import annotations

import math
from PIL import Image
from .overlay_canvas import OverlayDraw, FOCUSED_PRIMARY, draw_focus_ring
from .audio_profiles import audio_profiles, match_key


def percentage(value, maximum=100):
    try:
        number = float(value)
        return round(max(0.0, min(maximum/100, number))*100) if math.isfinite(number) else 100
    except (ValueError, TypeError):
        return 100


class MatchAudioPanel:
    WIDTH, HEIGHT = 600, 400
    SLIDERS = ((40, 126, 560, 160), (40, 231, 560, 265))
    CANCEL = (24, 310, 196, 358)
    GENERAL = (214, 310, 386, 358)
    MATCH = (404, 310, 576, 358)

    def __init__(self, selector):
        self.selector = selector
        app = selector.app
        self.runtime = audio_profiles(app)
        self.profile_path = self.runtime.path
        self._load_values(self.runtime.sync(force=True))
        self.focus = 0
        self.message = 'Arquivo de perfis indisponível; usando o volume geral.' if self.runtime.error else ''

    def _load_values(self, volumes):
        self.original_volumes = tuple(volumes)
        self.maximums = [200 if volumes[0] > 1 else 100, 100]
        self.values = [percentage(value, maximum) for value, maximum in zip(volumes, self.maximums)]
        self.original_values = list(self.values)

    def _volumes(self):
        # Preserve existing precision and amplification when a slider is untouched.
        return tuple(original if value == initial else value/100
                     for value, initial, original in zip(self.values, self.original_values, self.original_volumes))

    def buttons(self):
        result = [(2, self.CANCEL, 'Cancelar · F3'), (3, self.GENERAL, 'Aplicar geral · F1')]
        app = self.selector.app
        if self.runtime.path is not None and match_key(getattr(app, 'HID', ''), getattr(app, 'AID', '')):
            result.append((4, self.MATCH, 'Aplicar específico · F2'))
        return result

    def apply(self, scope='general'):
        selector = self.selector
        app = selector.app
        if (not selector.match_eligible() or selector.context != selector._context()
                or self.runtime.path != self.profile_path):
            selector.close()
            return
        try:
            if scope == 'general':
                volumes = self.runtime.apply_general(self._volumes())
            elif scope == 'match':
                volumes = self.runtime.apply_match(self._volumes())
            else:
                raise ValueError('Unknown audio profile scope')
        except Exception as exc:
            self.message = 'Não foi possível aplicar. Confira o arquivo e tente novamente.'
            app.log('Match audio settings could not be applied', exc)
            selector.render()
            return
        app.log(f'Match audio applied: scope={scope}; crowd={volumes[0]:.3f}; goal={volumes[1]:.3f}')
        selector.close()

    def activate(self, focus):
        if focus not in [item[0] for item in self.buttons()]:
            return
        if focus == 2:
            self.selector.close()
        else:
            self.apply({3: 'general', 4: 'match'}[focus])

    def handle(self, kind, value):
        if kind == 16:
            if value in (1,2,3):
                self.activate({1:3,2:4,3:2}[value])
            return
        focuses = [0, 1] + [focus for focus, rect, label in self.buttons()]
        if self.focus not in focuses:
            self.focus = 0
        if kind==15:
            x,y=value&65535,(value>>16)&65535
            targets=[(i,(rect[0]-10,rect[1]-15,rect[2]+10,rect[3]+15)) for i,rect in enumerate(self.SLIDERS)]
            targets.extend((focus, rect) for focus, rect, label in self.buttons())
            focus=next((focus for focus,rect in targets if rect[0]<=x<=rect[2] and rect[1]<=y<=rect[3]),None)
            if focus is not None and focus!=self.focus:
                self.focus=focus; self.selector.render()
            return
        if kind in (7, 11):
            self.selector.close()
            return
        if kind in (4, 5, 9):
            self.focus = focuses[(focuses.index(self.focus) + (-1 if kind == 4 else 1)) % len(focuses)]
        elif kind in (2, 3):
            if self.focus < 2:
                self.values[self.focus] = max(0, min(self.maximums[self.focus], self.values[self.focus] + (-5 if kind == 2 else 5)))
            else:
                focuses = [focus for focus, rect, label in self.buttons()]
                self.focus = focuses[(focuses.index(self.focus) + (-1 if kind == 2 else 1)) % len(focuses)]
        elif kind == 6:
            if self.focus >= 2:
                self.activate(self.focus)
                return
        elif kind in (8, 12):
            x, y = value & 65535, (value >> 16) & 65535
            for i, rect in enumerate(self.SLIDERS):
                if rect[0]-10 <= x <= rect[2]+10 and rect[1]-15 <= y <= rect[3]+15:
                    self.focus = i
                    maximum = self.maximums[i]
                    self.values[i] = max(0, min(maximum, round((x-rect[0])*maximum/(rect[2]-rect[0]))))
                    break
            else:
                if kind == 12:
                    return
                for focus, rect, label in self.buttons():
                    if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                        self.activate(focus)
                        return
        self.selector.render()

    def render(self):
        image = Image.new('RGBA', (self.WIDTH*2, self.HEIGHT*2))
        draw = OverlayDraw(image)
        blue, ink, muted = '#0968f8', '#344651', '#8797ab'
        draw.rounded_rectangle((0, 0, self.WIDTH-1, self.HEIGHT-1), 18, fill='white', outline='#e0e6ee')
        def text(x, y, label, size=17, color=ink, bold=False):
            draw.text((x, y), label, font=self.selector.font(size, bold), fill=color)
        def fit(label, size):
            font = self.selector.font(size)
            while len(label) > 1 and draw.textlength(label, font=font) > 550:
                label = label[:-2].rstrip('…') + '…'
            return label
        text(24, 22, 'Áudio da partida', 23, bold=True)
        text(390, 30, 'Áudios personalizados', 13, muted)
        app = self.selector.app
        key = match_key(getattr(app, 'HID', ''), getattr(app, 'AID', ''))
        names = []
        for team_id in (getattr(app, 'HID', ''), getattr(app, 'AID', '')):
            resolver = getattr(app, '_resolve_team_name', None)
            name = resolver(team_id) if callable(resolver) else ''
            names.append(str(name or team_id or '?'))
        caption = ('Confronto: ' if self.runtime.source == 'match' else 'Geral: ') + ' × '.join(names) if key else 'Perfil geral · áudios personalizados'
        text(24, 57, fit(caption, 15), 15, muted)
        for i, (label, rect) in enumerate(zip(('Cânticos da torcida', 'Hinos de gol'), self.SLIDERS)):
            text(40, rect[1]-35, label, 19, bold=True)
            text(503, rect[1]-35, f'{self.values[i]}%', 18, blue, True)
            cy = (rect[1]+rect[3])/2
            draw.rounded_rectangle((40, cy-4, 560, cy+4), 4, fill='#e4ecf7')
            x = 40+520*self.values[i]/self.maximums[i]
            if x > 40:
                draw.rounded_rectangle((40, cy-4, x, cy+4), 4, fill=blue)
            draw.ellipse((x-10, cy-10, x+10, cy+10), fill='white', outline=blue, width=3)
            if self.focus == i:
                draw_focus_ring(draw,(28, rect[1]-9, 572, rect[3]+1))
            text(40, rect[3]+8, '0', 12, muted)
            text(530, rect[3]+8, str(self.maximums[i]), 12, muted)
        for focus, rect, label in self.buttons():
            primary = focus == 4
            fill=FOCUSED_PRIMARY if primary and self.focus==focus else blue if primary else 'white'
            draw.rounded_rectangle(rect, 10, fill=fill, outline=blue if self.focus == focus else '#c9d3df', width=2)
            if self.focus == focus:
                draw_focus_ring(draw,rect)
            font = self.selector.font(14)
            draw.text(((rect[0]+rect[2]-draw.textlength(label, font=font))/2, rect[1]+(rect[3]-rect[1]-19)/2), label, font=font, fill='white' if primary else ink)
        text(24, 374, self.message or 'F1 Geral · F2 Específico · F3 / Esc Cancelar · ← → Volume · A Confirmar', 12, muted)
        return image
