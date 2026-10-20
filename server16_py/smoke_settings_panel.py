"""Draft smoke settings, committed by the parent presentation Apply action."""
from PIL import Image
from .overlay_canvas import OverlayDraw,draw_focus_ring
from .input_hints import navigation_hint,footer_y
from .panel_navigation import move_focus


class SmokeSettingsPanel:
    WIDTH,HEIGHT=600,620
    # Same global numbering as the native machineSites array (1 through 20).
    SIDELINES=((190,242),(190,482),(255,242),(255,482),
               (345,242),(345,482),(410,242),(410,482))
    REAR_ORDER=(12,8,14,16,10,18)

    def __init__(self,parent):
        self.parent=parent;self.selector=parent.selector;self.options=parent.options
        self.goal=False;self.focus=0

    def key(self,kind):return 'smoke_'+('goal' if self.goal else 'entrance')+'_'+kind

    def mask(self):return getattr(self.options,self.key('emitters'))

    def bit(self,index):return 1<<(index-8 if self.goal else index)

    def selected(self,index):return not(self.goal and index<8) and bool(self.mask()&self.bit(index))

    def positions(self):
        positions=dict(enumerate(self.SIDELINES))
        for row,index in enumerate(self.REAR_ORDER):
            positions[index]=(56,272+row*36);positions[index+1]=(544,272+row*36)
        return positions

    def targets(self):
        targets=[(0,(24,76,292,112)),(1,(308,76,576,112)),
                 (2,(414,126,456,164)),(3,(534,126,576,164))]
        targets.extend((4+i,(24+i*140,182,156+i*140,214)) for i in range(4))
        targets.extend((8+i,(x-14,y-14,x+14,y+14)) for i,(x,y) in sorted(self.positions().items()) if not(self.goal and i<8))
        return targets+[(28,(24,548,576,582))]

    def tick(self):pass

    def activate(self,focus):
        if focus==28:self.parent.close_smoke();return
        if focus in (0,1):self.goal=focus==1
        elif focus in (2,3):
            key=self.key('seconds');setattr(self.options,key,max(15,min(120,getattr(self.options,key)+(-5 if focus==2 else 5))))
        elif 4<=focus<=7:
            choices=(0xfff,0x555,0xaaa,0) if self.goal else (0xfffff,0xff,0xfff00,0)
            setattr(self.options,self.key('emitters'),choices[focus-4])
        elif 8<=focus<28:
            index=focus-8
            if self.goal and index<8:return
            setattr(self.options,self.key('emitters'),self.mask()^self.bit(index))
        self.selector.render()

    def handle(self,kind,value):
        if kind==11:self.selector.close();return
        if kind==7 or (kind==16 and value in (1,2)):self.parent.close_smoke();return
        if kind==6:self.activate(self.focus);return
        if kind in (2,3) and self.focus in (2,3):self.activate(2 if kind==2 else 3);return
        if kind in (2,3,4,5,9):self.focus=move_focus(self.focus,kind,self.targets())
        elif kind in (8,15):
            x,y=value&65535,(value>>16)&65535
            hit=next((i for i,r in self.targets() if r[0]<=x<=r[2] and r[1]<=y<=r[3]),None)
            if hit is None:return
            self.focus=hit
            if kind==8:self.activate(hit);return
        else:return
        self.selector.render()

    def render(self):
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2));draw=OverlayDraw(image)
        ink,muted,blue='#344651','#728397','#0968f8'
        draw.rounded_rectangle((0,0,599,619),18,fill='white',outline='#e0e6ee')
        def text(x,y,value,size=14,bold=False,color=ink):draw.text((x,y),value,font=self.selector.font(size,bold),fill=color)
        text(24,21,'Fumaça · tempo e emissores',23,True)
        text(24,55,'Escolha abaixo; depois volte e selecione Aplicar.',13,color=muted)
        targets=dict(self.targets())
        labels={0:'Na entrada',1:'Após gol do mandante',2:'−',3:'+',4:'Todos',
                5:'Gol esquerdo' if self.goal else 'Laterais',
                6:'Gol direito' if self.goal else 'Atrás dos gols',7:'Nenhum',28:'Voltar às configurações'}
        for focus,label in labels.items():
            rect=targets[focus];active=focus==(1 if self.goal else 0) and focus<2
            draw.rounded_rectangle(rect,8,fill=blue if active else '#f1f5fa',outline='#dbe3ed')
            if self.focus==focus:draw_focus_ring(draw,rect,8)
            size=13 if 4<=focus<=7 else 15
            width=draw.textlength(label,font=self.selector.font(size,True))
            text((rect[0]+rect[2]-width)/2,rect[1]+8,label,size,True,'white' if active else ink)
        text(24,129,'Duração total',16,True)
        text(24,151,'15 a 120 s · inclui a dissipação da fumaça',11,color=muted)
        text(472,135,f'{getattr(self.options,self.key("seconds"))} s',16,True)
        draw.rounded_rectangle((92,268,508,456),7,fill='#edf5f2',outline='#a9c5bb')
        draw.line((300,268,300,456),fill='#c2d5cd',width=1)
        draw.ellipse((269,332,331,394),outline='#c2d5cd',width=1)
        text(234,347,'CAMPO',17,True,'#90afa2')
        text(105,321,'GOL',11,color='#90afa2');text(467,321,'GOL',11,color='#90afa2')
        for index,(x,y) in self.positions().items():
            available=not(self.goal and index<8);active=self.selected(index)
            rect=(x-14,y-14,x+14,y+14)
            draw.ellipse(rect,fill=blue if active else '#e4eaf1',outline='#bac9db' if available else '#e4eaf1')
            label=str(index+1);width=draw.textlength(label,font=self.selector.font(12,True))
            text(x-width/2,y-8,label,12,True,'white' if active else ink if available else '#aebbc8')
            if self.focus==8+index:draw_focus_ring(draw,rect,14)
        count=self.mask().bit_count();total=12 if self.goal else 20
        text(24,506,f'{count} de {total} emissores ligados · azul = ligado',13,color=muted)
        if self.focus>=8 and self.focus<28:
            index=self.focus-8;location='lateral do campo' if index<8 else 'atrás do gol esquerdo' if index%2==0 else 'atrás do gol direito'
            text(24,525,f'Máquina {index+1} · {location}',12,color=muted)
        navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Alternar','Voltar')
        return image
