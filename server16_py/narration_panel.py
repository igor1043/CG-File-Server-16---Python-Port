from PIL import Image,ImageDraw,ImageOps
from .overlay_canvas import OverlayDraw, draw_focus_ring
from .input_hints import action_label,navigation_hint,footer_y, panel_function_key
from .narrator_portrait import portrait_image
from .narration_runtime import narration_runtime
from .panel_navigation import move_focus

class NarrationPanel:
    WIDTH,HEIGHT=600,390
    ROWS=((24,91,576,137),(24,148,576,194),(24,205,576,251))
    BACK,APPLY=(24,278,292,320),(308,278,576,320)
    def __init__(self,selector):
        self.selector=selector;self.runtime=narration_runtime(selector.app)
        self.options=self.runtime.profiles();self.index=next((i for i,p in enumerate(self.options) if p['name']==self.runtime.current),0)
        self.offset=(self.index//3)*3
        self.focus=self.index-self.offset if self.options else 3;self.message='';self.waiting=False
    def tick(self):
        if self.waiting:
            if self.runtime.pending is None:
                self.waiting=False
                if not self.runtime.error:
                    self.selector.show_menu()
                    # Runtime owns its independent progress and completion card.
                    return
                self.message=self.runtime.error
                self.selector.render()
            elif self.runtime.error and self.message!=self.runtime.error:
                self.message=self.runtime.error;self.selector.render()
    def activate(self,focus):
        if self.waiting:return
        if focus==3:self.selector.show_menu()
        elif focus==4:
            if not self.options:return
            if self.selector.context!=self.selector._context():self.selector.close();return
            try:
                self.runtime.apply(self.options[self.index]['name']);self.waiting=True;self.message='Aplicando narração…'
            except Exception as exc:self.message=str(exc)
            self.selector.render()
        elif 0<=focus<3 and self.offset+focus<len(self.options):
            self.index=self.offset+focus
            self.activate(4)
    def handle(self,kind,value):
        if kind==11:self.selector.close();return
        if kind==7:self.selector.show_menu();return
        if kind==16:
            if value in (1,2):self.activate(self.focus if value==1 else 3)
            return
        visible=self.options[self.offset:self.offset+3]
        targets=[(i,r) for i,r in enumerate(self.ROWS[:len(visible)])]+[(3,self.BACK),(4,self.APPLY)]
        focuses=[f for f,r in targets]
        if kind in (13,14):
            self.offset=max(0,min(max(0,len(self.options)-3),self.offset+(-3 if kind==13 else 3)))
            self.focus=min(self.focus,len(self.options[self.offset:self.offset+3])-1) if self.options else 3
        elif kind==5 and self.focus==len(visible)-1 and self.offset+3<len(self.options):self.offset+=1
        elif kind==4 and self.focus==0 and self.offset>0:self.offset-=1
        elif kind in (2,3,4,5,9):self.focus=move_focus(self.focus,kind,targets,4)
        elif kind==6:self.activate(self.focus);return
        elif kind in (8,15):
            x,y=value&65535,(value>>16)&65535
            if kind==8 and len(self.options)>3 and 578<=x<=592 and 91<=y<=251:
                self.offset=min(len(self.options)-3,max(0,round((y-91)*(len(self.options)-3)/160)))
                self.focus=0;self.index=self.offset;self.selector.render();return
            for f,r in targets:
                if r[0]<=x<=r[2] and r[1]<=y<=r[3]:
                    self.focus=f
                    if kind==8:self.activate(f);return
                    break
        if self.focus<len(visible):self.index=self.offset+self.focus
        self.selector.render()
    def render(self):
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2));draw=OverlayDraw(image)
        ink,muted,blue='#344651','#8797ab','#0968f8'
        draw.rounded_rectangle((0,0,self.WIDTH-1,self.HEIGHT-1),18,fill='white',outline='#e0e6ee')
        def text(x,y,label,size=16,color=ink,bold=False,width=None):
            draw.text((x,y),label,font=self.selector.font(size,bold),fill=color,max_width=576-x if width is None else width)
        text(24,22,'Narração da partida',23,bold=True);text(24,58,'Escolha antes de entrar em campo.',15,muted)
        if len(self.options)>3:text(470,58,f'{self.offset+1}–{min(self.offset+3,len(self.options))} / {len(self.options)}',13,muted)
        if len(self.options)>3:
            draw.rounded_rectangle((581,91,587,251),3,fill='#e4ecf7')
            thumb=160*3/len(self.options)
            top=91+160*self.offset/len(self.options)
            draw.rounded_rectangle((581,top,587,top+thumb),3,fill=blue)
        for i,(p,r) in enumerate(zip(self.options[self.offset:self.offset+3],self.ROWS)):
            draw.rounded_rectangle(r,9,fill='#f5f8fc',outline='#dce5ee')
            if self.focus==i:draw_focus_ring(draw,r,9)
            draw.ellipse((r[0]+14,r[1]+14,r[0]+31,r[1]+31),outline=blue,width=2)
            if self.index==i+self.offset:draw.ellipse((r[0]+18,r[1]+18,r[0]+27,r[1]+27),fill=blue)
            portrait=p.get('portrait')
            if portrait:
                try:
                    photo=portrait_image(portrait,p['name'])
                    draw.ellipse((65,r[1]+5,103,r[1]+43),fill='white',outline='#dce5ee',width=1)
                    image.alpha_composite(photo,(132,r[1]*2+12))
                except (OSError,ValueError):pass
            left=116 if portrait else 72
            text(left,r[1]+9,p['name'],17,bold=True,width=286-left)
            text(302,r[1]+12,p['commentator'],13,muted,width=167 if p['name']==self.runtime.current else 258)
            if p['name']==self.runtime.current:text(485,r[1]+12,'Atual',13,blue)
        if not self.options:text(24,115,'Crie uma subpasta por narrador em Narrations.',16,muted)
        for f,r,label,key,pad in ((3,self.BACK,'Voltar',panel_function_key(2),'B'),(4,self.APPLY,'Aplicar',panel_function_key(1),'A')):
            draw.rounded_rectangle(r,10,fill=blue if f==4 else 'white',outline=blue)
            if self.focus==f:draw_focus_ring(draw,r)
            action_label(draw,self.selector,r,label,key,pad,'white' if f==4 else ink)
        if self.message:text(24,footer_y(self.HEIGHT),self.message[:84],11,muted)
        else:navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Aplicar','Voltar')
        return image
