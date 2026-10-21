from __future__ import annotations

import math
import time
from pathlib import Path
from PIL import Image
from .overlay_canvas import OverlayDraw, FOCUSED_PRIMARY, draw_focus_ring
from .audio_profiles import audio_profiles, match_key
from .input_hints import action_label, navigation_hint, footer_y, panel_function_key
from .cloth_motion_switch import ClothMotionSwitch


def percentage(value, maximum=100):
    try:
        number = float(value)
        return round(max(0.0, min(maximum/100, number))*100) if math.isfinite(number) else 100
    except (ValueError, TypeError):
        return 100


class MatchAudioPanel:
    WIDTH, HEIGHT = 600, 495
    SLIDERS = ((40, 126, 560, 160), (40, 231, 560, 265))
    CLOTH = (24, 300, 576, 340)
    CANCEL = (24, 365, 196, 413)
    GENERAL = (214, 365, 386, 413)
    MATCH = (404, 365, 576, 413)

    def __init__(self, selector, *, on_back=None, include_cloth=True):
        self.selector = selector
        self.on_back = on_back or selector.close
        self.include_cloth = include_cloth
        app = selector.app
        self.runtime = audio_profiles(app)
        self.profile_path = self.runtime.path
        self._load_values(self.runtime.sync(force=True))
        self.focus = 0
        self.message = 'Arquivo de perfis indisponível; usando o volume geral.' if self.runtime.error else ''
        self.cloth = ClothMotionSwitch(getattr(app, 'exedir', getattr(app, 'base_dir', Path.cwd())))
        self.cloth_enabled = self.cloth.enabled()
        self.cloth_pending = None
        self.cloth_deadline = 0
        self.cloth_next_tick = 0

    def tick(self):
        if not self.include_cloth:return
        now=time.monotonic()
        if now<self.cloth_next_tick:return
        self.cloth_next_tick=now+.25
        resolver=getattr(self.selector.app,'_resolve_fifa_pid',None)
        pid=resolver() if callable(resolver) else None
        live=self.cloth.live_enabled(pid=pid)
        if self.cloth_pending is not None:
            if live==self.cloth_pending:
                self.message='Física de roupas ativada.' if live else 'Física de roupas desativada.'
                self.cloth_pending=None;self.selector.render()
            elif now>=self.cloth_deadline:
                self.message='Opção salva. Reabra o FIFA para carregar o controle atualizado.'
                self.cloth_pending=None;self.selector.render()
        elif live is not None and live!=self.cloth_enabled:
            self.cloth_enabled=live;self.selector.render()

    def toggle_cloth(self):
        if not self.include_cloth:return
        if not self.cloth.available():return
        if not self.selector.match_eligible() or self.selector.context!=self.selector._context():
            self.selector.close();return
        try:
            self.cloth.set_enabled(not self.cloth_enabled)
        except (OSError,ValueError) as exc:
            self.message='Não foi possível alterar a física de roupas.'
            self.selector.app.log('Cloth physics live switch failed',exc)
        else:
            self.cloth_enabled=not self.cloth_enabled
            self.cloth_pending=self.cloth_enabled
            self.cloth_deadline=time.monotonic()+3
            self.message='Aplicando física de roupas…'
        self.selector.render()

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
        result = [(2, self.CANCEL, 'Cancelar'), (3, self.GENERAL, 'Aplicar geral')]
        app = self.selector.app
        if self.runtime.path is not None and match_key(getattr(app, 'HID', ''), getattr(app, 'AID', '')):
            result.append((4, self.MATCH, 'Aplicar específico'))
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
        self.on_back()

    def activate(self, focus):
        if focus==5:
            self.toggle_cloth();return
        if focus not in [item[0] for item in self.buttons()]:
            return
        if focus == 2:
            self.on_back()
        else:
            self.apply({3: 'general', 4: 'match'}[focus])

    def handle(self, kind, value):
        if kind == 18:
            if value in (1,2):
                self.activate({1:3,2:4}[value])
            return
        if kind == 16:
            if value in (1,2,3):
                self.activate({1:3,2:4,3:2}[value])
            return
        focuses = [0, 1] + ([5] if self.include_cloth and self.cloth.available() else []) + [focus for focus, rect, label in self.buttons()]
        if self.focus not in focuses:
            self.focus = 0
        if kind==15:
            x,y=value&65535,(value>>16)&65535
            targets=[(i,(rect[0]-10,rect[1]-15,rect[2]+10,rect[3]+15)) for i,rect in enumerate(self.SLIDERS)]
            targets.extend((focus, rect) for focus, rect, label in self.buttons())
            if self.include_cloth and self.cloth.available():targets.append((5,self.CLOTH))
            focus=next((focus for focus,rect in targets if rect[0]<=x<=rect[2] and rect[1]<=y<=rect[3]),None)
            if focus is not None and focus!=self.focus:
                self.focus=focus; self.selector.render()
            return
        if kind in (7, 11):
            self.selector.close() if kind==11 else self.on_back()
            return
        if kind in (4, 5, 9):
            self.focus = focuses[(focuses.index(self.focus) + (-1 if kind == 4 else 1)) % len(focuses)]
        elif kind in (2, 3):
            if self.focus < 2:
                self.values[self.focus] = max(0, min(self.maximums[self.focus], self.values[self.focus] + (-5 if kind == 2 else 5)))
            elif self.focus==5:
                self.toggle_cloth();return
            else:
                focuses = [focus for focus, rect, label in self.buttons()]
                self.focus = focuses[(focuses.index(self.focus) + (-1 if kind == 2 else 1)) % len(focuses)]
        elif kind == 6:
            if self.focus >= 2:
                self.activate(self.focus)
                return
        elif kind in (8, 12):
            x, y = value & 65535, (value >> 16) & 65535
            if self.include_cloth and kind==8 and self.CLOTH[0]<=x<=self.CLOTH[2] and self.CLOTH[1]<=y<=self.CLOTH[3]:
                self.focus=5;self.toggle_cloth();return
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
            draw.text((x, y), label, font=self.selector.font(size, bold), fill=color,max_width=576-x)
        def fit(label, size):
            font = self.selector.font(size)
            while len(label) > 1 and draw.textlength(label, font=font) > 550:
                label = label[:-2].rstrip('…') + '…'
            return label
        text(24, 22, 'Música' if not self.include_cloth else 'Ajustes da partida', 23, bold=True)
        text(350, 30, 'Torcida, cânticos e hinos' if not self.include_cloth else 'Áudio e física de roupas', 13, muted)
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
        if self.include_cloth:
            rect=self.CLOTH;active=self.cloth_enabled;available=self.cloth.available()
            if self.focus==5:draw_focus_ring(draw,rect,8)
            draw.text((36,311),'Física de roupas · aplica agora',font=self.selector.font(16),fill=ink if available else muted,max_width=427)
            draw.rounded_rectangle((479,308,525,332),12,fill=blue if active and available else '#d6dee9')
            cx=513 if active else 491;draw.ellipse((cx-9,311,cx+9,329),fill='white')
            text(535,311,'Sim' if active else 'Não',12,ink if available else muted)
        for focus, rect, label in self.buttons():
            primary = focus == 4
            fill=FOCUSED_PRIMARY if primary and self.focus==focus else blue if primary else 'white'
            draw.rounded_rectangle(rect, 10, fill=fill, outline=blue if self.focus == focus else '#c9d3df', width=2)
            if self.focus == focus:
                draw_focus_ring(draw,rect)
            key, pad_button = {2:(panel_function_key(3),'B'),3:(panel_function_key(1),'X'),4:(panel_function_key(2),'Y')}[focus]
            action_label(draw,self.selector,rect,label,key,pad_button,'white' if primary else ink,size=12)
        if self.message:
            text(24,footer_y(self.HEIGHT),self.message,12,muted)
        else:
            navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Confirmar','Cancelar')
        return image
