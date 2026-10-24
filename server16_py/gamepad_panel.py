"""Shared desktop/in-game controller setup, backed by the single SDL worker."""
from __future__ import annotations
import time
from PIL import Image
from .overlay_canvas import OverlayDraw, draw_focus_ring
from .input_hints import navigation_hint
from .gamepad_mapping import MappingCapture, STEPS, mapped_state


def bridge_for(app):
    bridge=getattr(app, 'gamepad_bridge', None)
    if bridge is None:
        from .gamepad_bridge_runtime import GamepadBridgeRuntime
        from .hidhide_runtime import HidHideRuntime
        app.hidhide=HidHideRuntime(app)
        bridge=app.gamepad_bridge=GamepadBridgeRuntime(app)
        bridge.start()
    return bridge


class GamepadPanel:
    WIDTH, HEIGHT = 900, 650

    def __init__(self, selector, on_back=None):
        self.selector=selector; self.app=selector.app; self.bridge=bridge_for(self.app)
        self.on_back=on_back or selector.close
        self.slot=0; self.focus=0; self.page='home'; self.message=''
        self.devices=[]; self.device_page=0; self.raw=None; self.capture=None
        self._next=0.; self._signature=None

    def snapshot(self): return self.bridge.get_slot_snapshot(self.slot)

    def targets(self):
        tabs=[(100+i,(24+i*216,88,228+i*216,132)) for i in range(4)]
        if self.page=='devices':
            return tabs+[(200+i,(24,156+i*48,876,198+i*48)) for i,_ in enumerate(self.devices[self.device_page*7:(self.device_page+1)*7])]+[(30,(24,512,270,554)),(31,(286,512,532,554)),(9,(24,568,270,610))]
        if self.page=='capture':return [(8,(24,498,300,546)),(9,(316,498,592,546))]
        labels=self.labels()
        return tabs+[(i,(24,154+i*51,340,198+i*51)) for i in range(len(labels))]

    def labels(self):
        s=self.snapshot()
        return ['Escolher controle', 'Mapear botões e analógicos',
                'Desativar ponte' if s['enabled'] else 'Ativar ponte no FIFA',
                'Perfil: '+('Personalizado' if s['profile']=='custom' else 'Automático SDL'),
                'Desocultar controle físico' if s['hide_from_fifa'] else 'Evitar entrada dupla · HidHide',
                'Instalar driver Xbox virtual', 'Instalar HidHide (opcional)', 'Voltar']

    def tick(self):
        now=time.monotonic()
        if now<self._next:return
        self._next=now+.05
        s=self.snapshot(); guid=s['device_guid']
        if self.page=='devices': self.devices=self.bridge.list_devices()
        self.raw=self.bridge.read_raw_state(guid,self.slot) if guid else None
        if self.page=='capture' and self.capture.observe(self.raw):
            if self.capture.done:
                self.bridge.set_mapping(guid,self.capture.result())
                self.bridge.set_slot_config(self.slot,enabled=s['enabled'],device_guid=guid,profile='custom')
                self.page='home'; self.focus=2
                self.message='Perfil salvo. Ative a ponte e confira os comandos à direita.'
        signature=(repr(self.raw),repr(s),self.page,self.capture.index if self.capture else 0,tuple(d.guid for d in self.devices),self.message)
        if signature!=self._signature:
            self._signature=signature; self.selector.render()

    def activate(self, action):
        if 100<=action<104:
            self.slot=action-100; self.focus=0; self.raw=None; self.page='home'
        elif self.page=='devices' and 200<=action<207:
            index=self.device_page*7+action-200
            if index<len(self.devices):
                d=self.devices[index]; s=self.snapshot()
                self.bridge.set_slot_config(self.slot,enabled=False,device_guid=d.guid,profile='auto',hide_from_fifa=False)
                self.page='home'; self.focus=1; self.message=d.name
        elif self.page=='devices' and action in (30,31):
            self.device_page=max(0,min(max(0,(len(self.devices)-1)//7),self.device_page+(-1 if action==30 else 1)))
        elif self.page=='capture' and action==8:
            self.capture.skip()
            if self.capture.done:
                s=self.snapshot();self.bridge.set_mapping(s['device_guid'],self.capture.result())
                self.bridge.set_slot_config(self.slot,enabled=s['enabled'],device_guid=s['device_guid'],profile='custom')
                self.page='home';self.focus=2
        elif action==9 or self.page=='home' and action==7:
            if self.page!='home': self.page='home';self.capture=None;self.focus=0
            else:self.on_back();return
        elif self.page=='home':
            s=self.snapshot();guid=s['device_guid']
            if action==0:
                self.page='devices'; self.devices=self.bridge.list_devices(); self.device_page=0; self.focus=200 if self.devices else 9
            elif action==1:
                if not guid:self.message='Escolha primeiro um controle físico.'
                else:self.capture=MappingCapture();self.page='capture';self.focus=8;self.message='Solte todos os botões e deixe os analógicos no centro.'
            elif action==2:
                if not guid:self.message='Escolha primeiro um controle físico.'
                elif not self.bridge.dependencies_available():self.message='Instale o driver Xbox virtual e reabra o Server16 para ativar.'
                else:self.bridge.set_slot_config(self.slot,enabled=not s['enabled'],device_guid=guid,profile=s['profile'])
            elif action==3:
                profile='auto' if s['profile']=='custom' else 'custom'
                if profile=='custom' and guid not in self.app.settings.data.get('gamepad_mappings',{}):self.message='Mapeie este controle antes de usar o perfil personalizado.'
                else:self.bridge.set_slot_config(self.slot,enabled=s['enabled'],device_guid=guid,profile=profile)
            elif action==4:
                if not guid:self.message='Escolha primeiro um controle físico.'
                elif not self.app.hidhide.is_hidhide_installed():self.message='Instale o HidHide para evitar que o FIFA receba duas entradas.'
                else:self.bridge.set_slot_config(self.slot,enabled=s['enabled'],device_guid=guid,profile=s['profile'],hide_from_fifa=not s['hide_from_fifa'])
            elif action in (5,6):
                self.message='Aguardando a confirmação do instalador do driver…'
                def done(success,message):
                    self.message=('Driver instalado. Reabra o Server16.' if success else message)
                    self.selector.render()
                if action==5:self.bridge.install_vigembus(done)
                else:self.app.hidhide.install_hidhide(done)
        self.selector.render()

    def handle(self,kind,value):
        if kind==11:self.on_back();return
        if self.page=='capture':
            # Physical A/B are being learned; they cannot also leave the wizard.
            if kind==16 and value==2:self.activate(8)
            elif kind==8:
                x,y=value&65535,(value>>16)&65535
                for action,r in self.targets():
                    if r[0]<=x<=r[2] and r[1]<=y<=r[3]:self.activate(action);break
            return
        if kind==7:self.activate(9);return
        targets=self.targets();keys=[a for a,_ in targets]
        if kind in (8,15):
            x,y=value&65535,(value>>16)&65535
            target=next((a for a,r in targets if r[0]<=x<=r[2] and r[1]<=y<=r[3]),None)
            if target is None:return
            self.focus=target
            if kind==8:self.activate(target);return
        elif kind in (4,5,9):
            current=keys.index(self.focus) if self.focus in keys else 0
            self.focus=keys[(current+(-1 if kind==4 else 1))%len(keys)]
        elif kind in (2,3,13,14):
            if self.page=='devices':self.activate(30 if kind in (2,13) else 31);return
            self.activate(100+(self.slot+(-1 if kind in (2,13) else 1))%4);return
        elif kind==6:self.activate(self.focus);return
        self.selector.render()

    def render(self):
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2));d=OverlayDraw(image)
        d.rounded_rectangle((0,0,899,649),18,fill='#f6f8fa',outline='#d6dfe8')
        def text(x,y,s,size=17,color='#344651',bold=False,width=840):
            d.text((x,y),str(s),font=self.selector.font(size,bold),fill=color,max_width=width)
        text(24,20,'CONTROLES',27,bold=True)
        text(24,58,'Controle genérico → Xbox 360 · perfis salvos por dispositivo',15,'#728397')
        s=self.snapshot()
        for i in range(4):
            r=(24+i*216,88,228+i*216,132)
            d.rounded_rectangle(r,6,fill='#0968f8' if i==self.slot else '#e0e7ee')
            text(r[0]+18,99,f'Jogador {i+1}',17,'white' if i==self.slot else '#344651',True,180)
        targets=dict(self.targets())
        if self.page=='devices':
            for i,device in enumerate(self.devices[self.device_page*7:(self.device_page+1)*7]):
                r=targets[200+i];d.rounded_rectangle(r,6,fill='white',outline='#d6dfe8')
                text(40,r[1]+8,device.name,18,width=810)
            if not self.devices:text(30,170,'Nenhum controle genérico conectado. Controles Xbox usam o suporte nativo.',17,width=810)
            for key,label in ((30,'Anterior'),(31,'Próxima'),(9,'Voltar')):
                r=targets[key];d.rounded_rectangle(r,6,fill='#e0e7ee');text(r[0]+16,r[1]+10,label)
        elif self.page=='capture':
            c=self.capture
            text(30,170,f'PASSO {min(c.index+1,len(STEPS))} DE {len(STEPS)}',16,'#0968f8',True)
            text(30,216,STEPS[c.index][1] if not c.done else 'Concluído',30,bold=True,width=825)
            text(30,282,'Acione o comando indicado. Solte antes de passar para o próximo.',18)
            text(30,321,'Gatilhos e analógicos: mova até o fim, depois volte ao repouso.',17)
            d.rounded_rectangle((30,388,870,410),8,fill='#dce6f1')
            if c.index:d.rounded_rectangle((30,388,30+840*c.index/len(STEPS),410),8,fill='#0968f8')
            for key,label in ((8,'Pular comando · F4'),(9,'Cancelar mapeamento')):
                r=targets[key];d.rounded_rectangle(r,6,fill='#e0e7ee');text(r[0]+14,r[1]+12,label,17,width=r[2]-r[0]-24)
        else:
            for i,label in enumerate(self.labels()):
                r=targets[i];d.rounded_rectangle(r,6,fill='white',outline='#d6dfe8')
                text(38,r[1]+13,label,16,width=290)
            d.rounded_rectangle((360,154,876,554),12,fill='white',outline='#d6dfe8')
            names={x.guid:x.name for x in self.bridge.list_devices()}
            text(382,174,names.get(s['device_guid'],'Escolha um controle físico'),19,bold=True,width=472)
            states={'active':'Ativo no FIFA','busy':'Aguardando dispositivo','disconnected':'Desconectado'}
            text(382,207,states.get(s['status'],s['status']) if s['enabled'] else 'Ponte desativada · suporte Xbox nativo preservado',14,'#0968f8',width=470)
            raw=self.raw or {};mapping=self.app.settings.data.get('gamepad_mappings',{}).get(s['device_guid'],{})
            if s['profile']=='custom':state=mapped_state(raw,mapping)
            elif raw.get('mapped'):state=raw['mapped']
            else:
                from .gamepad_bridge_runtime import resolve_mapped_state
                state=resolve_mapped_state(raw,self.bridge.resolve_profile(names.get(s['device_guid'],''),s['device_guid'],s['profile']))
            d.rounded_rectangle((409,270,827,426),45,fill='#e5ebf1',outline='#bccbd9')
            for button,x,y in [('Y',755,292),('X',722,325),('B',788,325),('A',755,358)]:
                pressed=state['buttons'].get('XUSB_GAMEPAD_'+button,False)
                d.ellipse((x-19,y-19,x+19,y+19),fill='#0968f8' if pressed else 'white',outline='#a7b8c9')
                text(x-6,y-11,button,17,'white' if pressed else '#344651',True)
            for key,x,y in [('left_stick',489,325),('right_stick',644,379)]:
                d.ellipse((x-30,y-30,x+30,y+30),fill='#ced9e4')
                vx,vy=state[key];d.ellipse((x-12+vx*20,y-12-vy*20,x+12+vx*20,y+12-vy*20),fill='#344651')
            for key,x in [('left_trigger',423),('right_trigger',686)]:
                d.rounded_rectangle((x,242,x+118,254),4,fill='#e0e7ee')
                if state[key]>0:d.rounded_rectangle((x,242,x+max(3,118*state[key]),254),4,fill='#0968f8')
            pressed=[k.replace('XUSB_GAMEPAD_','') for k,v in state['buttons'].items() if v]
            text(382,453,'Botões: '+(', '.join(pressed) or 'nenhum'),14,width=470)
            text(382,492,'Xbox / XInput: use diretamente, sem criar outra ponte.',13,'#728397',width=470)
            text(382,517,'HidHide é opcional e evita o físico + virtual ao mesmo tempo.',12,'#728397',width=470)
        if self.focus in targets:draw_focus_ring(d,targets[self.focus])
        if self.message:text(24,584,self.message,14,'#0968f8',width=850)
        if self.page=='capture':text(24,624,'F4: pular comando · F12: fechar · clique em Cancelar para sair',13,'#728397')
        else:navigation_hint(d,self.selector,620,'Selecionar','Voltar')
        return image


def build_desktop_tab(app, parent):
    import tkinter as tk
    from types import SimpleNamespace
    from PIL import ImageTk, ImageFont
    host=tk.Canvas(parent,bg=app.bg,highlightthickness=0);host.pack(fill='both',expand=True)
    fonts={}
    def font(size,bold=False):
        key=(size,bold)
        if key not in fonts:fonts[key]=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',size*2)
        return fonts[key]
    selector=SimpleNamespace(app=app,font=font,controller_connected=False)
    panel=None; scale=1.; origin=(0,0)
    def render():
        nonlocal scale,origin
        if panel is None:return
        image=panel.render();w=max(1,host.winfo_width());h=max(1,host.winfo_height())
        scale=min(w/panel.WIDTH,h/panel.HEIGHT);origin=((w-panel.WIDTH*scale)/2,(h-panel.HEIGHT*scale)/2)
        image=image.resize((max(1,round(panel.WIDTH*scale)),max(1,round(panel.HEIGHT*scale))),Image.Resampling.LANCZOS)
        host.photo=ImageTk.PhotoImage(image);host.delete('all');host.create_image(*origin,anchor='nw',image=host.photo)
    selector.render=render;selector.close=lambda:app.tabview.select(app.dashboard_tab)
    def ensure():
        nonlocal panel
        if panel is None:panel=GamepadPanel(selector)
        return panel
    def click(event):
        p=ensure();x=round((event.x-origin[0])/scale);y=round((event.y-origin[1])/scale)
        p.handle(8,(y<<16)|(x&65535))
    host.bind('<Button-1>',click);host.bind('<Configure>',lambda e:render())
    host.bind('<Enter>',lambda e:host.focus_set())
    for key,kind in [('Up',4),('Down',5),('Left',2),('Right',3),('Return',6),('Escape',7)]:host.bind('<'+key+'>',lambda e,k=kind:ensure().handle(k,0))
    host.bind('<F4>',lambda e:ensure().handle(16,2))
    def tick():
        if getattr(app,'_shutdown_complete',False):return
        if str(app.tabview.select())==str(parent):ensure().tick();render()
        app.after(60,tick)
    app.after(100,tick)
