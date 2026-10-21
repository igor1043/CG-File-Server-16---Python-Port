"""Menu panorama settings, before opening the stadium browser."""
from PIL import Image
from .overlay_canvas import OverlayDraw, draw_focus_ring
from .frontend_stadium_selection import enabled, save_enabled
from .input_hints import navigation_hint


class FrontendStadiumPanel:
    SCALE=0.9
    WIDTH,HEIGHT=540,396

    def __init__(self,selector):
        self.selector=selector
        self.focus=0
        self.enabled=enabled(selector.app.exedir)
        self.message=''
        self.career=selector._frontend_career
        self._layout_height=520 if self.career else 440
        self.HEIGHT=round(self._layout_height*self.SCALE)

    def targets(self):
        rows=[(0,(24,100,576,185))]
        if self.enabled:rows.append((1,(24,205,576,283)))
        if self.career:rows.append((3,(24,300,576,360)))
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
        elif kind in (2,3) and self.focus==0:self.activate(0);return
        elif kind==6:self.activate(self.focus);return
        elif kind==16:
            self.activate(0 if value==1 else 1 if value==2 else 2);return
        self.selector.render()

    def render(self):
        selector=self.selector
        height=self._layout_height
        image=Image.new('RGBA',(1200,height*2))
        draw=OverlayDraw(image)
        draw.rounded_rectangle((0,0,599,height-1),18,fill='white',outline='#e0e6ee')
        def text(x,y,value,size=17,color='#344651',bold=False):
            draw.text((x,y),value,font=selector.font(size,bold),fill=color)
        text(24,22,'ESTÁDIO DE FUNDO',25,bold=True)
        text(24,61,'Carreira: clube do save • Início: time favorito',15,'#8797ab')
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
                text(42,217,'Escolher estádio',20,bold=True)
                text(42,250,'A escolha só muda quando você clicar em Aplicar.',14,'#8797ab')
            elif i==3:text(42,316,'Ferramentas da carreira',18)
            else:text(42,height-104,'Voltar ao FIFA',18)
        if self.message:text(24,height-145,self.message,14,'#0968f8')
        navigation_hint(draw,selector,height-38)
        return image.resize((self.WIDTH*2,self.HEIGHT*2),Image.Resampling.LANCZOS)
