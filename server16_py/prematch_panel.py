from __future__ import annotations

import time
from PIL import Image
from .overlay_canvas import OverlayDraw, FOCUSED_PRIMARY, draw_focus_ring
from .input_hints import action_label, navigation_hint, controller_connected, footer_y, panel_function_key
from .match_settings_panel import MatchSettingsPanel
from .narration_panel import NarrationPanel
from .panel_navigation import move_focus
from .extra_scenes_panel import ExtraScenesPanel
import server16_py as features


class PrematchPanel:
    WIDTH, HEIGHT = 600, 390
    BACK = (24, 278, 576, 320)

    def __init__(self, selector, crowd=False):
        self.selector = selector
        self.crowd = crowd
        rows = (len(self.cards())+1)//2
        self.HEIGHT = 390 if crowd else 193+rows*129
        self.BACK = (24,278,576,320) if crowd else (24,self.HEIGHT-101,576,self.HEIGHT-59)
        self.focus = 0
        self.column = 0
        self.message = ''
        self.command = None
        self.deadline = 0
        shared = selector.crowd_control.shared
        self.value = shared.current_percent if shared.ack==shared.command and 0 <= shared.current_percent <= 100 else None
        self.dirty = False

    def cards(self):
        items = [(0, ('Controle de','público')), (1, ('Escolha seu','estádio')),
                 (2, ('Configurações','da partida')), (6, ('Configurar','controles'))]
        if features.NARRATION_PICKER_AVAILABLE:items.append((3, ('Escolha os','narradores')))
        if features.EXTRA_SCENES_AVAILABLE:items.append((4, ('Cenas extras','Técnico e mascote')))
        cards = []
        for position,(action,labels) in enumerate(items):
            left = 24 if position%2==0 else 309
            right = 576 if position==len(items)-1 and position%2==0 else left+267
            top = 91+(position//2)*129
            cards.append((action,(left,top,right,top+114),labels))
        return cards

    def back(self):
        self.selector.show_menu()

    def tick(self):
        if not self.crowd:
            return
        shared = self.selector.crowd_control.shared
        if self.command is not None:
            if shared.ack == self.command and shared.status == 3:
                self.selector.app.log(f'Manual attendance applied: {self.value}% for current fixture')
                self.selector.show_menu()
                return
            if shared.status == 4 or time.monotonic() >= self.deadline:
                self.selector.crowd_control.clear()
                self.command = None
                self.message = 'Não foi possível confirmar o público. A regra automática foi mantida.'
                self.selector.render()
        elif (not self.dirty and shared.ack==shared.command and
              0 <= shared.current_percent <= 100 and self.value != shared.current_percent):
            self.value = shared.current_percent
            self.selector.render()

    def activate(self, focus):
        if self.command is not None:
            return
        selector = self.selector
        if not self.crowd:
            if focus != 5 and focus not in {action for action,_,_ in self.cards()}:return
            if focus == 0:
                selector.prematch_panel = PrematchPanel(selector, crowd=True)
                selector.render()
            elif focus == 1:
                if not selector.app.module_enabled('Stadium'):
                    self.message='Ative o módulo de estádios no Server para usar esta opção.'
                    selector.render()
                    return
                selector.open()
                selector.return_to_menu = True
            elif focus == 2:
                selector.prematch_panel = MatchSettingsPanel(selector)
                selector.render()
            elif focus == 3:
                selector.prematch_panel = NarrationPanel(selector)
                selector.render()
            elif focus == 4:
                selector.prematch_panel = ExtraScenesPanel(self, prematch=True)
                selector.render()
            elif focus == 6:
                selector.open_gamepads()
            else:
                selector.close()
        elif focus == 1:
            selector.show_menu()
        elif focus == 2:
            try:
                if self.value is None or selector.context[:3] != selector._context()[:3]:
                    raise RuntimeError('No current attendance value')
                self.command = selector.crowd_control.apply(self.value, selector.context)
                self.deadline = time.monotonic()+3
                self.message = 'Aplicando público...'
            except Exception as exc:
                self.message = 'Público indisponível: aguarde o mod de torcida e tente novamente.'
                selector.app.log('Manual attendance request rejected', exc)
            selector.render()

    def handle(self, kind, value):
        selector = self.selector
        if kind == 11:
            selector.close()
            return
        if kind == 7 or (kind == 16 and self.crowd and value == 3):
            selector.show_menu() if self.crowd else selector.close()
            return
        if kind == 16:
            if not self.crowd:
                cards = self.cards()
                if 1 <= value <= len(cards):self.activate(cards[value-1][0])
            elif value == 1:
                self.activate(2)
            elif value == 2:
                self.activate(1)
            return
        targets = [(0, (40, 148, 560, 190)), (1, (24, 278, 292, 320)), (2, (308, 278, 576, 320))] if self.crowd else [(action, rect) for action,rect,_ in self.cards()]+[(5,self.BACK)]
        if kind in (8, 12, 15):
            x, y = value & 65535, (value >> 16) & 65535
            target = next((focus for focus, rect in targets if rect[0]<=x<=rect[2] and rect[1]<=y<=rect[3]), None)
            if target is None:
                return
            if kind == 12 and (not self.crowd or target != 0):
                return
            self.focus = target
            if self.crowd and target == 0 and kind in (8,12) and self.value is not None and self.command is None:
                self.value = max(0,min(100,round((x-40)*100/520)))
                self.dirty = True
            elif kind == 8:
                self.activate(target)
                return
        elif kind in (4, 5, 9):
            self.focus = move_focus(self.focus,kind,targets,2+self.column if not self.crowd else 2)
        elif kind in (2, 3):
            direction = -1 if kind==2 else 1
            if self.crowd and self.focus==0 and self.value is not None and self.command is None:
                self.value=max(0,min(100,self.value+direction*5)); self.dirty=True
            elif self.crowd and self.focus>0:
                self.focus = 1 if direction<0 else 2
            else:
                self.focus=move_focus(self.focus,kind,targets)
        elif kind == 6:
            self.activate(self.focus)
            return
        if not self.crowd and self.focus<4:self.column=self.focus%2
        selector.render()

    def render(self):
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2))
        draw=OverlayDraw(image)
        blue, ink, muted = '#0968f8', '#344651', '#8797ab'
        draw.rounded_rectangle((0,0,599,self.HEIGHT-1),18,fill='white',outline='#e0e6ee')
        def text(x,y,label,size=17,color=ink,bold=False):
            font=self.selector.font(size,bold)
            while label and draw.textlength(label,font=font)>576-x:
                label=label[:-2].rstrip('…')+'…'
            draw.text((x,y),label,font=font,fill=color)
        def button(rect,label,focus,key,pad_button,primary=False):
            selected=self.focus==focus
            draw.rounded_rectangle(rect,10,fill=FOCUSED_PRIMARY if primary and selected else blue if primary else 'white',outline=blue if selected else '#c9d3df')
            if selected: draw_focus_ring(draw,rect)
            action_label(draw,self.selector,rect,label,key,pad_button,'white' if primary else ink,show_icon=self.crowd)
        text(24,22,'Público da partida' if self.crowd else 'Prepare sua partida',23,bold=True)
        text(24,59,'Uma alteração manual vale somente para esta partida.' if self.crowd else 'Escolha o que deseja ajustar antes de entrar em campo.',15,muted)
        if not self.crowd:
            for shortcut,(i,rect,labels) in enumerate(self.cards(),1):
                draw.rounded_rectangle(rect,14,fill='#f5f8fc',outline='#dce5ee')
                if self.focus==i: draw_focus_ring(draw,rect,14)
                cx=rect[0]+53
                top=rect[1]-91
                if i==0:
                    for dx,dy in ((-27,8),(0,0),(27,8)):
                        draw.ellipse((cx+dx-8,123+dy+top,cx+dx+8,139+dy+top),outline=blue,width=2)
                        draw.arc((cx+dx-15,143+dy+top,cx+dx+15,173+dy+top),180,360,fill=blue,width=3)
                elif i==1:
                    draw.ellipse((cx-35,128+top,cx+35,157+top),outline=blue,width=3)
                    draw.ellipse((cx-24,135+top,cx+24,148+top),outline=blue,width=2)
                    draw.arc((cx-35,140+top,cx+35,170+top),0,180,fill=blue,width=3)
                elif i==2:
                    for dy,dx in ((0,-15),(15,13),(30,-3)):
                        draw.line((cx-30,129+dy+top,cx+30,129+dy+top),fill=blue,width=3)
                        draw.ellipse((cx+dx-6,123+dy+top,cx+dx+6,135+dy+top),fill='white',outline=blue,width=2)
                elif i==3:
                    draw.rounded_rectangle((cx-11,120+top,cx+11,156+top),11,outline=blue,width=3)
                    draw.arc((cx-22,139+top,cx+22,171+top),0,180,fill=blue,width=3)
                    draw.line((cx,172+top,cx,183+top),fill=blue,width=3)
                elif i==6:
                    draw.rounded_rectangle((cx-34,130+top,cx+34,172+top),14,outline=blue,width=3)
                    draw.line((cx-23,151+top,cx-5,151+top),fill=blue,width=3)
                    draw.line((cx-14,142+top,cx-14,160+top),fill=blue,width=3)
                    for dx,dy in ((14,146),(24,156)):
                        draw.ellipse((cx+dx-3,top+dy-3,cx+dx+3,top+dy+3),fill=blue)
                else:
                    draw.rounded_rectangle((cx-30,127+top,cx+15,163+top),6,outline=blue,width=3)
                    draw.line(((cx+15,138+top),(cx+32,129+top),(cx+32,161+top),(cx+15,152+top),(cx+15,138+top)),fill=blue,width=3)
                font=self.selector.font(16,True)
                for row,label in enumerate(labels):
                    draw.text((rect[0]+108,rect[1]+29+row*22),label,font=font,fill=ink)
                if not controller_connected(self.selector) and shortcut<=5:
                    text(rect[0]+108,rect[1]+80,panel_function_key(shortcut),13,muted)
            button(self.BACK,'Fechar',5,'Esc','B')
        else:
            shared=self.selector.crowd_control.shared
            text(40,104,'Ocupação do estádio',19,bold=True)
            text(504,104,f'{self.value}%' if self.value is not None else '—',20,blue,True)
            draw.rounded_rectangle((40,165,560,173),4,fill='#e4ecf7')
            if self.value is not None:
                x=40+520*self.value/100
                if x>40: draw.rounded_rectangle((40,165,x,173),4,fill=blue)
                draw.ellipse((x-10,159,x+10,179),fill='white',outline=blue,width=3)
            if self.focus==0: draw_focus_ring(draw,(28,141,572,197))
            text(40,205,'0%',12,muted); text(524,205,'100%',12,muted)
            automatic=f'Regra atual do mod: {shared.automatic_percent}%' if shared.automatic_percent>=0 else 'Aguardando o valor atual do mod de torcida...'
            text(40,230,automatic,14,muted)
            button((24,278,292,320),'Voltar',1,panel_function_key(2),'B')
            button((308,278,576,320),'Aplicar',2,panel_function_key(1),'A',True)
        if self.message:
            text(24,footer_y(self.HEIGHT),self.message,11,muted)
        else:
            navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Confirmar' if self.crowd else 'Abrir','Voltar' if self.crowd else 'Fechar')
        return image
