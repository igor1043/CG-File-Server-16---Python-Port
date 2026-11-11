"""Menu panorama settings, before opening the stadium browser."""
from PIL import Image
from .overlay_canvas import OverlayDraw, draw_focus_ring
from .frontend_stadium_selection import (
    IDLE_BACKGROUNDS, IDLE_BACKGROUND_LABELS, background_mode, idle_background,
    save_background_mode, save_idle_background,
)
from .input_hints import navigation_hint
from .native_feature_switch import UltrawideSwitch
from .career_feedback import show_ultrawide_restart


class FrontendStadiumPanel:
    SCALE=0.9
    WIDTH,HEIGHT=540,396

    def __init__(self,selector):
        self.selector=selector
        self.focus=0
        self.mode=background_mode(selector.app.exedir)
        self.idle_mode=idle_background(selector.app.exedir)
        self.ultrawide=UltrawideSwitch(selector.app.exedir)
        self.message=''
        self.career=selector._frontend_career
        self.screen_settings=False
        self._layout_height=780 if self.career else 620
        self.HEIGHT=round(self._layout_height*self.SCALE)

    @property
    def enabled(self):return self.mode=='stadium'
    @enabled.setter
    def enabled(self,value):self.mode='stadium' if value else 'image'

    def shift_background(self,step=1):
        choices=('image','stadium','dressing_room') if self.career else ('image','stadium')
        current=self.mode if self.mode in choices else 'stadium'
        value=choices[(choices.index(current)+step)%len(choices)]
        try:
            save_background_mode(self.selector.app.exedir,value)
            self.mode=value
            self.message={'image':'Imagem de fundo ativada.','stadium':'Estádio 3D ativado.','dressing_room':'Preparando o vestiário do clube atual…'}[value]
        except OSError as error:
            self.message='Não foi possível salvar a opção.';self.selector.app.log(self.message,error)
        self.selector.render()

    def targets(self):
        if self.screen_settings:
            self._layout_height=340;self.HEIGHT=round(self._layout_height*self.SCALE)
            return [(5,(24,100,576,178)),(2,(24,self._layout_height-115,576,self._layout_height-65))]
        ids=[0]+([6] if self.career else [])+([1] if self.enabled else [])+[7]+([3] if self.career else [])+[4]
        rows=[];y=100
        for i in ids:
            height=78 if i in (0,6) else 54
            rows.append((i,(24,y,576,y+height)));y+=height+14
        self._layout_height=y+146;self.HEIGHT=round(self._layout_height*self.SCALE)
        return rows+[(2,(24,self._layout_height-115,576,self._layout_height-65))]

    def activate(self,focus):
        selector=self.selector
        if focus==0:
            self.shift_background()
        elif focus==1 and self.enabled:selector.open(frontend=True,career=self.career,frontend_picker=True)
        elif focus==2:
            if self.screen_settings:self.screen_settings=False;self.focus=7;self.message='';selector.render()
            else:selector.close()
        elif focus==7:self.screen_settings=True;self.focus=5;self.message='';selector.render()
        elif focus==3 and self.career:selector.open(career=True)
        elif focus==4:selector.open_gamepads()
        elif focus==6 and self.career:
            value=IDLE_BACKGROUNDS[1-IDLE_BACKGROUNDS.index(self.idle_mode)]
            try:
                save_idle_background(selector.app.exedir,value)
            except OSError as error:
                self.message='Não foi possível salvar a opção.';selector.app.log(self.message,error)
            else:
                self.idle_mode=value
                self.message='Fundo de espera salvo.'
            selector.render()
        elif focus==5 and self.screen_settings:
            try:
                active=not self.ultrawide.enabled()
                self.ultrawide.set_enabled(active)
            except (OSError,ValueError) as error:
                self.message='Não foi possível aplicar o ultrawide.';selector.app.log(self.message,error)
            else:
                self.message=show_ultrawide_restart(selector.app, active)
            selector.render()

    def handle(self,kind,value):
        if kind in (7,11) or kind==16 and value==3:self.activate(2);return
        targets=self.targets()
        if kind in (8,15):
            x,y=(value&65535)/self.SCALE,((value>>16)&65535)/self.SCALE
            focus=next((i for i,r in targets if r[0]<=x<=r[2] and r[1]<=y<=r[3]),None)
            if focus is None:return
            self.focus=focus
            if kind==8:
                if focus==0:self.shift_background(-1 if x<310 else 1)
                else:self.activate(focus)
                return
        elif kind in (4,5,9):
            keys=[i for i,r in targets];index=keys.index(self.focus) if self.focus in keys else 0
            self.focus=keys[(index+(-1 if kind==4 else 1))%len(keys)]
        elif kind in (2,3) and self.focus in (0,5,6):
            if self.focus==0:self.shift_background(-1 if kind==2 else 1)
            else:self.activate(self.focus)
            return
        elif kind==6:self.activate(self.focus);return
        elif kind==16:
            action=({4:5} if self.screen_settings else {1:0,2:1,4:7}).get(value)
            if action is not None:self.activate(action)
            return
        self.selector.render()

    def render(self):
        selector=self.selector
        targets=self.targets()
        height=self._layout_height
        image=Image.new('RGBA',(1200,height*2))
        draw=OverlayDraw(image)
        draw.rounded_rectangle((0,0,599,height-1),18,fill='white',outline='#e0e6ee')
        def text(x,y,value,size=17,color='#344651',bold=False):
            draw.text((x,y),value,font=selector.font(size,bold),fill=color)
        text(24,22,'CONFIGURAÇÕES DE TELA' if self.screen_settings else 'CONFIGURAÇÕES VISUAIS',25,bold=True)
        text(24,61,'Proporção da imagem' if self.screen_settings else 'Personalize o fundo e a visualização',15,'#8797ab')
        for i,r in targets:
            y=r[1]
            draw.rounded_rectangle(r,10,fill='#f6f1e7' if self.focus==i else 'white',outline='#c9d3df')
            if i==self.focus:
                x1,y1,x2,y2=r
                draw.rounded_rectangle((x1-4,y1-4,x2+4,y2+4),14,outline='#b9a274',width=3)
            if i==0:
                text(42,y+10,'Fundo da carreira' if self.career else 'Fundo do menu',19,bold=True)
                labels={'image':'Imagem de fundo','stadium':'Estádio 3D','dressing_room':'Vestiário 3D'}
                text(42,y+44,'‹',25,'#8a744b',True)
                text(81,y+46,labels.get(self.mode,'Estádio 3D'),18,'#344651',True)
                text(526,y+44,'›',25,'#8a744b',True)
            elif i==1:
                text(42,y+16,'Escolher estádio',20,bold=True)
                text(536,y+16,'›',20,'#8a744b',True)
            elif i==5:
                active=self.ultrawide.enabled()
                text(42,y+12,'Ultrawide',20,bold=True)
                text(42,y+45,'Reinicie o FIFA após alterar.',14,'#8797ab')
                draw.rounded_rectangle((470,y+22,548,y+56),17,fill='#b9a274' if active else '#a9b6c6')
                center=531 if active else 487
                draw.ellipse((center-13,y+26,center+13,y+52),fill='white')
            elif i==6:
                text(42,y+10,'Fundo de espera da carreira',19,bold=True)
                text(42,y+44,'‹',22,'#8a744b',True)
                text(81,y+45,IDLE_BACKGROUND_LABELS[IDLE_BACKGROUNDS.index(self.idle_mode)],17,bold=True)
                text(526,y+44,'›',22,'#8a744b',True)
            elif i==7:text(42,y+16,'Configurações de tela',18,bold=True);text(536,y+16,'›',20,'#8a744b',True)
            elif i==3:text(42,y+16,'Ferramentas da carreira',18)
            elif i==4:text(42,y+16,'Configurar controles',18)
            else:text(42,y+11,'Voltar às configurações visuais' if self.screen_settings else 'Voltar ao FIFA',18)
        if self.message:text(24,height-145,self.message,14,'#0968f8')
        navigation_hint(draw,selector,height-38)
        return image.resize((self.WIDTH*2,self.HEIGHT*2),Image.Resampling.LANCZOS)
