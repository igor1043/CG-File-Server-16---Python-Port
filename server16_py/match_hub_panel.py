"""In-match categories rendered by the existing Select+Start overlay."""
from __future__ import annotations
import time
from PIL import Image
from .overlay_canvas import OverlayDraw, draw_focus_ring
from .input_hints import navigation_hint, footer_y, panel_function_key
from .match_audio_panel import MatchAudioPanel
from .cloth_motion_switch import ClothMotionSwitch
from .first_person_runtime import first_person_runtime, fov_limits, HEAD_SMOOTHING
from .extra_scenes_panel import ExtraScenesPanel
import server16_py as features


class MatchHubPanel:
    WIDTH, HEIGHT = 600, 490

    def __init__(self, selector):
        self.selector = selector
        self.page = 'home'
        self.child = None
        self.focus = 0
        self.message = ''
        self._last_status = None
        self._next_tick = 0
        self.cloth = ClothMotionSwitch(getattr(selector.app, 'exedir', selector.app.base_dir))
        self.cloth_value = self.cloth.enabled()
        self.cloth_pending = False
        self.cloth_deadline = 0

    def back(self):
        self.page = 'home'
        self.child = None
        self.focus = 0
        self.message = ''
        self.selector.render()

    def camera(self):
        return first_person_runtime(self.selector.app)

    def items(self):
        if self.page == 'home':
            items = [('Música', 'Cânticos, torcida e hinos de gol'),
                    ('Gráficos', 'Física de roupas'),
                    ('Câmera', 'Primeira pessoa e terceira pessoa · carreira')]
            if features.EXTRA_SCENES_AVAILABLE:
                items.append(('Cenas extras', 'Técnico e mascote · rosto ou corpo inteiro'))
            return items + [('Fechar', 'Voltar à partida')]
        if self.page == 'graphics':
            live = self.cloth.live_enabled(pid=self.selector.app._resolve_fifa_pid())
            value = self.cloth_value if live is None else live
            return [('Física de roupas', 'Ligada' if value else 'Desligada'), ('Voltar', 'Ajustes da partida')]
        runtime = self.camera()
        items = [('Câmera do jogador', ('Ligada' if runtime.enabled else 'Desligada') + ' · escolha salva'),
                ('Modo', 'Terceira pessoa · carreira' if runtime.mode else 'Primeira pessoa'),
                ('Campo de visão', f'{runtime.fov}° · esquerda / direita ajustam 5°')]
        if runtime.mode:items.append(('Distância', ('Perto','Intermediária','Afastada')[runtime.distance]))
        else:items.append(('Suavização da cabeça', HEAD_SMOOTHING[runtime.profile]))
        return items + [('Voltar', 'Ajustes da partida')]

    def targets(self):
        pitch, height = (58,48) if self.page in ('home','camera') and len(self.items())==5 else (72,60)
        return [(i, (24, 98+i*pitch, 576, 98+i*pitch+height)) for i in range(len(self.items()))]

    def tick(self):
        if self.child:
            self.child.tick()
            return
        now = time.monotonic()
        if now < self._next_tick:return
        self._next_tick = now + .25
        if self.page == 'camera':
            runtime = self.camera()
            status = (runtime.status(), runtime.enabled, runtime.fov, runtime.mode, runtime.distance, runtime.profile)
        elif self.page == 'graphics':
            live = self.cloth.live_enabled(pid=self.selector.app._resolve_fifa_pid())
            if self.cloth_pending:
                if live == self.cloth_value:
                    self.cloth_pending = False
                    self.message = 'Física de roupas aplicada.'
                elif now >= self.cloth_deadline:
                    self.cloth_pending = False
                    self.message = 'Opção salva. Reinicie o FIFA para atualizar o módulo.'
            status = (live, self.message)
        else:return
        if status != self._last_status:
            self._last_status = status
            self.selector.render()

    def activate(self, index, direction=1):
        if not self.selector.match_eligible() or self.selector.context != self.selector._context():
            self.selector.close();return
        if self.page == 'home':
            if index == 0:
                self.child = MatchAudioPanel(self.selector, on_back=self.back, include_cloth=False)
                self.child.HEIGHT = self.HEIGHT
            elif index in (1, 2):
                self.page = 'graphics' if index == 1 else 'camera'
            elif index == 3 and features.EXTRA_SCENES_AVAILABLE:
                self.child = ExtraScenesPanel(self)
            else:
                self.selector.close();return
            self.focus = 0
        elif index == len(self.items())-1:
            self.back();return
        else:
            try:
                if self.page == 'graphics':
                    if not self.cloth.available():raise RuntimeError('Módulo de física de roupas indisponível.')
                    self.cloth_value = not self.cloth_value
                    self.cloth.set_enabled(self.cloth_value)
                    self.cloth_pending = True
                    self.cloth_deadline = time.monotonic()+3
                    self.message = 'Aplicando física de roupas…'
                else:
                    runtime = self.camera()
                    if index == 0:runtime.configure(enabled=not runtime.enabled)
                    elif index == 1:runtime.configure(mode=1-runtime.mode)
                    elif index == 2:
                        low, high = fov_limits(runtime.mode)
                        runtime.configure(fov=max(low,min(high,runtime.fov+direction*5)))
                    elif index == 3 and runtime.mode:runtime.configure(distance=(runtime.distance+direction)%3)
                    elif index == 3:runtime.configure(head_smoothing=(runtime.profile+direction)%len(HEAD_SMOOTHING))
                    self.message=''
            except (OSError, RuntimeError, ValueError) as exc:
                self.message = str(exc)
                self.selector.app.log('Match settings could not be applied', exc)
        self.selector.render()

    def handle(self, kind, value):
        if self.child:
            self.child.handle(kind, value);return
        if kind == 11:self.selector.close();return
        if kind == 7:
            self.selector.close() if self.page == 'home' else self.back();return
        if kind == 16:
            index = value-1
            if 0 <= index < len(self.items()):self.activate(index)
            return
        targets = self.targets()
        if kind in (4, 5, 9):self.focus=(self.focus+(-1 if kind==4 else 1))%len(targets)
        elif kind in (2,3) and self.page != 'home':
            self.activate(self.focus,-1 if kind==2 else 1);return
        elif kind == 6:self.activate(self.focus);return
        elif kind in (8,15):
            x,y=value&65535,(value>>16)&65535
            focus=next((i for i,r in targets if r[0]<=x<=r[2] and r[1]<=y<=r[3]),None)
            if focus is None:return
            self.focus=focus
            if kind==8:self.activate(focus);return
        else:return
        self.selector.render()

    def render(self):
        if self.child:return self.child.render()
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2))
        draw=OverlayDraw(image)
        draw.rounded_rectangle((0,0,599,489),18,fill='white',outline='#e0e6ee')
        ink,muted,blue='#344651','#728397','#0968f8'
        title={'home':'Ajustes da partida','graphics':'Gráficos','camera':'Câmera'}[self.page]
        draw.text((24,22),title,font=self.selector.font(24,True),fill=ink)
        caption={'home':'Personalize sem sair do jogo','graphics':'Ajustes disponíveis durante a partida',
                 'camera':'No FIFA, selecione a câmera Profissional.'}[self.page]
        draw.text((24,59),caption,font=self.selector.font(15),fill=muted)
        for (index,rect),(label,detail) in zip(self.targets(),self.items()):
            draw.rounded_rectangle(rect,10,fill='#f4f7fb',outline='#dbe3ed')
            if self.focus==index:draw_focus_ring(draw,rect)
            available=470 if not self.selector.controller_connected else 520
            draw.text((40,rect[1]+9),label,font=self.selector.font(18,True),fill=ink,max_width=available)
            draw.text((40,rect[1]+31),detail,font=self.selector.font(13),fill=muted,max_width=available)
            if not self.selector.controller_connected:
                draw.text((527,rect[1]+21),panel_function_key(index+1),font=self.selector.font(13,True),fill=blue)
        message=self.message
        if self.page == 'camera' and not message:message=self.camera().status()
        if self.page=='camera':
            draw.text((24,400),'Visão de campo e bola · ajustes salvos automaticamente',font=self.selector.font(13),fill=muted)
        if message:
            # Fit status on one line without clipping the controller hints.
            while len(message)>1 and draw.textlength(message,font=self.selector.font(12))>550:message=message[:-2]+'…'
            draw.text((24,425),message,font=self.selector.font(12),fill=muted)
        navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Abrir' if self.page=='home' else 'Alterar','Fechar' if self.page=='home' else 'Voltar')
        return image
