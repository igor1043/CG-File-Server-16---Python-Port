from __future__ import annotations

import time
from PIL import Image
from .overlay_canvas import OverlayDraw, FOCUSED_PRIMARY, draw_focus_ring


class PrematchPanel:
    WIDTH, HEIGHT = 600, 350
    CARDS = ((24, 91, 292, 256), (308, 91, 576, 256))
    BACK = (24, 278, 576, 320)

    def __init__(self, selector, crowd=False):
        self.selector = selector
        self.crowd = crowd
        self.focus = 0
        self.message = ''
        self.command = None
        self.deadline = 0
        shared = selector.crowd_control.shared
        self.value = shared.current_percent if shared.ack==shared.command and 0 <= shared.current_percent <= 100 else None
        self.dirty = False

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
        if kind == 7 or (kind == 16 and value == 3):
            selector.show_menu() if self.crowd else selector.close()
            return
        if kind == 16:
            if not self.crowd:
                self.activate(value-1)
            elif value == 1:
                self.activate(2)
            elif value == 2:
                self.activate(1)
            return
        targets = [(0, (40, 148, 560, 190)), (1, (24, 278, 292, 320)), (2, (308, 278, 576, 320))] if self.crowd else [(i, rect) for i, rect in enumerate(self.CARDS)]+[(2,self.BACK)]
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
            self.focus = (self.focus+(-1 if kind==4 else 1)) % 3
        elif kind in (2, 3):
            direction = -1 if kind==2 else 1
            if self.crowd and self.focus==0 and self.value is not None and self.command is None:
                self.value=max(0,min(100,self.value+direction*5)); self.dirty=True
            elif self.crowd and self.focus>0:
                self.focus = 1 if direction<0 else 2
            else:
                self.focus=(self.focus+direction)%3
        elif kind == 6:
            self.activate(self.focus)
            return
        selector.render()

    def render(self):
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2))
        draw=OverlayDraw(image)
        blue, ink, muted = '#0968f8', '#344651', '#8797ab'
        draw.rounded_rectangle((0,0,599,349),18,fill='white',outline='#e0e6ee')
        def text(x,y,label,size=17,color=ink,bold=False):
            font=self.selector.font(size,bold)
            while label and draw.textlength(label,font=font)>576-x:
                label=label[:-2].rstrip('…')+'…'
            draw.text((x,y),label,font=font,fill=color)
        def button(rect,label,focus,primary=False):
            selected=self.focus==focus
            draw.rounded_rectangle(rect,10,fill=FOCUSED_PRIMARY if primary and selected else blue if primary else 'white',outline=blue if selected else '#c9d3df')
            if selected: draw_focus_ring(draw,rect)
            font=self.selector.font(16)
            draw.text(((rect[0]+rect[2]-draw.textlength(label,font=font))/2,rect[1]+11),label,font=font,fill='white' if primary else ink)
        text(24,22,'Público da partida' if self.crowd else 'Prepare sua partida',23,bold=True)
        text(24,59,'Uma alteração manual vale somente para esta partida.' if self.crowd else 'Escolha o que deseja ajustar antes de entrar em campo.',15,muted)
        if not self.crowd:
            for i,(rect,label) in enumerate(zip(self.CARDS,('Controle de público','Escolha seu estádio'))):
                draw.rounded_rectangle(rect,14,fill='#f5f8fc',outline='#dce5ee')
                if self.focus==i: draw_focus_ring(draw,rect,14)
                cx=(rect[0]+rect[2])/2
                if i==0:
                    for dx,dy in ((-27,8),(0,0),(27,8)):
                        draw.ellipse((cx+dx-8,123+dy,cx+dx+8,139+dy),outline=blue,width=2)
                        draw.arc((cx+dx-15,143+dy,cx+dx+15,173+dy),180,360,fill=blue,width=3)
                else:
                    draw.ellipse((cx-35,128,cx+35,157),outline=blue,width=3)
                    draw.ellipse((cx-24,135,cx+24,148),outline=blue,width=2)
                    draw.arc((cx-35,140,cx+35,170),0,180,fill=blue,width=3)
                font=self.selector.font(18,True)
                draw.text((cx-draw.textlength(label,font=font)/2,191),label,font=font,fill=ink)
                text(cx-12,225,f'F{i+1}',13,muted)
            button(self.BACK,'Fechar · Esc / F3',2)
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
            button((24,278,292,320),'Voltar · Esc / F2',1)
            button((308,278,576,320),'Aplicar · F1',2,True)
        status = self.message or ('← → Ajustar · Enter / A Confirmar · B Voltar' if self.crowd else 'Setas Selecionar · Enter / A Abrir · B Fechar')
        text(24,330,status,11,muted)
        return image
