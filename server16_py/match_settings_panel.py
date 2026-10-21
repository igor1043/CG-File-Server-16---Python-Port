from PIL import Image

from .input_hints import action_label, navigation_hint, footer_y, panel_function_key
from .match_presentation import MatchPresentation, PresentationOptions
from .overlay_canvas import OverlayDraw, FOCUSED_PRIMARY, draw_focus_ring
from .panel_navigation import move_focus
from .cloth_motion_switch import ClothMotionSwitch, _atomic
from .smoke_settings_panel import SmokeSettingsPanel


class MatchSettingsPanel:
    WIDTH, HEIGHT = 600, 545
    ROWS = ((24, 85, 576, 120), (24, 130, 576, 165),
            (48, 175, 576, 210), (48, 220, 576, 255), (24, 265, 576, 300), (24, 310, 576, 345), (24,355,576,397))
    BACK, APPLY = (24, 427, 292, 469), (308, 427, 576, 469)

    def __init__(self, selector):
        self.selector = selector
        self.focus = 0
        self.message = ''
        self.load_error = False
        self.child = None
        self.store = MatchPresentation(getattr(selector.app, 'exedir', selector.app.base_dir))
        self.cloth = ClothMotionSwitch(getattr(selector.app, 'exedir', selector.app.base_dir))
        self.cloth_enabled = self.cloth_original = self.cloth.enabled()
        try:
            self.options = self.store.load()
        except Exception as exc:
            self.options = PresentationOptions()
            self.load_error = True
            self.message = 'Configuração inválida. Corrija o INI antes de aplicar.'
            selector.app.log('Match presentation config rejected', exc)

    def tick(self):
        pass

    def close_smoke(self):
        self.child=None;self.HEIGHT=545;self.focus=6;self.selector.render()

    def enabled(self, focus):
        if focus == 5:
            return self.cloth.available()
        return focus not in (2, 3) or self.options.pyrotechnics

    def activate(self, focus):
        if focus == len(self.ROWS):
            self.selector.show_menu()
        elif focus == len(self.ROWS) + 1:
            if self.load_error:
                return
            if self.selector.context != self.selector._context():
                self.selector.close()
                return
            try:
                previous = self.store.path.read_bytes() if self.store.path.exists() else None
                self.store.save(self.options)
                try:
                    if self.cloth_enabled != self.cloth_original:
                        self.cloth.set_enabled(self.cloth_enabled)
                except Exception:
                    if previous is None:
                        self.store.path.unlink(missing_ok=True)
                    else:
                        _atomic(self.store.path, previous)
                    raise
            except Exception as exc:
                self.message = 'Não foi possível aplicar. Confira a permissão da pasta.'
                self.selector.app.log('Match presentation could not be saved', exc)
                self.selector.render()
                return
            self.selector.app.log(f'Match presentation applied: {self.options}')
            self.selector.show_menu()
        elif focus==6:
            self.child=SmokeSettingsPanel(self);self.HEIGHT=self.child.HEIGHT;self.selector.render()
        elif self.enabled(focus):
            if focus == 5:
                self.cloth_enabled = not self.cloth_enabled
            else:
                key = self.store.KEYS[focus]
                setattr(self.options, key, not getattr(self.options, key))
            self.selector.render()

    def handle(self, kind, value):
        if self.child:self.child.handle(kind,value);return
        if kind == 11:
            self.selector.close()
            return
        if kind == 7 or (kind == 16 and value == 2):
            self.selector.show_menu()
            return
        if kind == 16:
            if value == 1:
                self.activate(len(self.ROWS) + 1)
            return
        focuses = [i for i in range(len(self.ROWS) + 2) if self.enabled(i)]
        if kind in (4, 5, 9, 2, 3):
            targets=[(i,r) for i,r in enumerate((*self.ROWS,self.BACK,self.APPLY)) if i in focuses]
            self.focus = move_focus(self.focus,kind,targets,len(self.ROWS) + 1)
        elif kind == 6:
            self.activate(self.focus)
            return
        elif kind in (8, 15):
            x, y = value & 65535, (value >> 16) & 65535
            for i, rect in enumerate((*self.ROWS, self.BACK, self.APPLY)):
                if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3] and self.enabled(i):
                    self.focus = i
                    if kind == 8:
                        self.activate(i)
                        return
                    break
        self.selector.render()

    def render(self):
        if self.child:return self.child.render()
        image = Image.new('RGBA', (self.WIDTH*2, self.HEIGHT*2))
        draw = OverlayDraw(image)
        ink, muted, blue = '#344651', '#8797ab', '#0968f8'
        draw.rounded_rectangle((0, 0, self.WIDTH-1, self.HEIGHT-1), 18, fill='white', outline='#e0e6ee')
        draw.text((24, 22), 'Configurações da partida', font=self.selector.font(23, True), fill=ink)
        draw.text((24, 58), 'Apresentação, efeitos e física das roupas.', font=self.selector.font(15), fill=muted)
        labels = ('Habilitar mascotes', 'Fumaça e pirotecnia', 'Na entrada da partida', 'Após o gol do mandante', 'Objetos de abertura da competição', 'Física de roupas · camisa e calção', 'Fumaça · duração e emissores')
        for i, (label, rect) in enumerate(zip(labels, self.ROWS)):
            active = self.cloth_enabled if i == 5 else getattr(self.options, self.store.KEYS[i]) if i<5 else False
            enabled = self.enabled(i)
            if self.focus == i:
                draw_focus_ring(draw, rect, 8)
            draw.text((rect[0]+12, rect[1]+8), label, font=self.selector.font(16, i < 2), fill=ink if enabled else muted,
                      max_width=(484 if i==6 else 463)-(rect[0]+12))
            if i==6:
                draw.text((500,rect[1]+11),'Abrir ›',font=self.selector.font(13,True),fill=blue)
                continue
            cy = (rect[1]+rect[3])/2
            draw.rounded_rectangle((479, cy-12, 525, cy+12), 12, fill=blue if active and enabled else '#d6dee9')
            cx = 513 if active else 491
            draw.ellipse((cx-9, cy-9, cx+9, cy+9), fill='white')
            draw.text((535, cy-9), 'Sim' if active else 'Não', font=self.selector.font(12), fill=ink if enabled else muted)
        for focus, rect, label, key, button in ((len(self.ROWS), self.BACK, 'Voltar', panel_function_key(2), 'B'), (len(self.ROWS) + 1, self.APPLY, 'Aplicar', panel_function_key(1), 'A')):
            primary = focus == len(self.ROWS) + 1
            draw.rounded_rectangle(rect, 10, fill=FOCUSED_PRIMARY if primary and self.focus == focus else blue if primary else 'white', outline='#c9d3df')
            if self.focus == focus:
                draw_focus_ring(draw, rect)
            action_label(draw, self.selector, rect, label, key, button, 'white' if primary else ink)
        if self.message:
            draw.text((24, footer_y(self.HEIGHT)), self.message, font=self.selector.font(11), fill=muted,max_width=552)
        else:
            navigation_hint(draw, self.selector, footer_y(self.HEIGHT), 'Alternar / aplicar')
        return image
