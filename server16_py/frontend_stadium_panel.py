"""Menu panorama settings, before opening the stadium browser."""
from PIL import Image
from .overlay_canvas import OverlayDraw, draw_focus_ring
from .frontend_stadium_selection import enabled, save_enabled
from .input_hints import navigation_hint
from .native_feature_switch import UltrawideSwitch
from .career_feedback import show_ultrawide_restart


class FrontendStadiumPanel:
    SCALE=0.9
    WIDTH,HEIGHT=540,396

    def __init__(self,selector):
        self.selector=selector
        self.focus=0
        self.enabled=enabled(selector.app.exedir)
        self.ultrawide=UltrawideSwitch(selector.app.exedir)
        self.message=''
        self.career=selector._frontend_career
        self._layout_height=700 if self.career else 620
        self.HEIGHT=round(self._layout_height*self.SCALE)

    def targets(self):
        rows=[(0,(24,100,576,185)),(5,(24,205,576,265))]
        if self.enabled:rows.append((1,(24,285,576,363)))
        if self.career:rows.append((3,(24,380,576,440)))
        rows.append((4,(24,460 if self.career else 380,576,520 if self.career else 440)))
        return rows+[(2,(24,self._layout_height-115,576,self._layout_height-65))]

    def activate(self,focus):
        selector=self.selector
        if focus==0:
            try:
                save_enabled(selector.app.exedir,not self.enabled)
                self.enabled=not self.enabled
                self.message='Preparando o cenário…' if self.enabled else 'Fundo FIFA Friends ativado.'
            except OSError as error:
                self.message='Não foi possível salvar a opção.';selector.app.log(self.message,error)
            selector.render()
        elif focus==1 and self.enabled:selector.open(frontend=True,career=self.career,frontend_picker=True)
        elif focus==2:selector.close()
        elif focus==3 and self.career:selector.open(career=True)
        elif focus==4:selector.open_gamepads()
        elif focus==5:
            try:
                active=not self.ultrawide.enabled()
                self.ultrawide.set_enabled(active)
            except (OSError,ValueError) as error:
                self.message='Não foi possível aplicar o ultrawide.';selector.app.log(self.message,error)
            else:
                self.message=show_ultrawide_restart(selector.app, active)
            selector.render()

    def handle(self,kind,value):
        if kind in (7,11) or kind==16 and value==3:self.selector.close();return
        targets=self.targets()
        if kind in (8,15):
            x,y=(value&65535)/self.SCALE,((value>>16)&65535)/self.SCALE
            focus=next((i for i,r in targets if r[0]<=x<=r[2] and r[1]<=y<=r[3]),None)
            if focus is None:return
            self.focus=focus
            if kind==8:self.activate(focus);return
        elif kind in (4,5,9):
            keys=[i for i,r in targets];index=keys.index(self.focus) if self.focus in keys else 0
            self.focus=keys[(index+(-1 if kind==4 else 1))%len(keys)]
        elif kind in (2,3) and self.focus in (0,5):self.activate(self.focus);return
        elif kind==6:self.activate(self.focus);return
        elif kind==16:
            action={1:0,2:1,3:2,4:5}.get(value)
            if action is not None:self.activate(action)
            return
        self.selector.render()

    def render(self):
        selector=self.selector
        height=self._layout_height
        image=Image.new('RGBA',(1200,height*2))
        draw=OverlayDraw(image)
        draw.rounded_rectangle((0,0,599,height-1),18,fill='white',outline='#e0e6ee')
        def text(x,y,value,size=17,color='#344651',bold=False):
            draw.text((x,y),value,font=selector.font(size,bold),fill=color)
        text(24,22,'CONFIGURAÇÕES VISUAIS',25,bold=True)
        text(24,61,'Estádio de fundo e proporção da imagem',15,'#8797ab')
        for i,r in self.targets():
            draw.rounded_rectangle(r,10,fill='#eef4ff' if self.focus==i else 'white',outline='#c9d3df')
            if i==self.focus:draw_focus_ring(draw,r)
            if i==0:
                text(42,115,'Usar estádio personalizado',20,bold=True)
                draw.rounded_rectangle((470,115,548,149),17,fill='#0968f8' if self.enabled else '#a9b6c6')
                center=531 if self.enabled else 487
                draw.ellipse((center-13,119,center+13,145),fill='white')
                text(42,150,'Ative para usar o cenário 3D no fundo.',14,'#8797ab')
            elif i==1:
                text(42,297,'Escolher estádio',20,bold=True)
                text(42,330,'A escolha só muda quando você clicar em Aplicar.',14,'#8797ab')
            elif i==5:
                active=self.ultrawide.enabled()
                text(42,214,'Ultrawide',20,bold=True)
                text(42,244,'Reinicie o FIFA após alterar.',14,'#8797ab')
                draw.rounded_rectangle((470,219,548,253),17,fill='#b9a274' if active else '#a9b6c6')
                center=531 if active else 487
                draw.ellipse((center-13,223,center+13,249),fill='white')
            elif i==3:text(42,396,'Ferramentas da carreira',18)
            elif i==4:text(42,476 if self.career else 396,'Configurar controles',18)
            else:text(42,height-104,'Voltar ao FIFA',18)
        if self.message:text(24,height-145,self.message,14,'#0968f8')
        navigation_hint(draw,selector,height-38)
        return image.resize((self.WIDTH*2,self.HEIGHT*2),Image.Resampling.LANCZOS)
