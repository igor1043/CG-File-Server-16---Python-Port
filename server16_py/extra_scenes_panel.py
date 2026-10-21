"""Saved controls for the optional native extra-scenes director."""
from __future__ import annotations
import configparser
from pathlib import Path
import time
from PIL import Image
from .overlay_canvas import OverlayDraw, draw_focus_ring
from .input_hints import navigation_hint, footer_y, panel_function_key
from .stadium_catalog import prematch_page

VIEWS = ('Desligado', 'Corpo inteiro', 'Rosto', 'Alternar')
DEFAULTS = {'scenes': {'enabled':'1', 'coach_view':'3', 'mascot_view':'3',
    'cooldown_seconds':'45', 'chance_percent':'35', 'duration_ms':'5000',
    'coach_weight':'1', 'mascot_weight':'1',
    'test_mode':'0',
    'preview_serial':'0', 'preview_actor':'0'},
    'coach_full':{'distance':'600','fov':'26','height':'120','angle':'0'},
    'coach_face':{'distance':'600','fov':'12','height':'170','angle':'0'},
    'mascot_full':{'distance':'850','fov':'24','height':'120','angle':'0'},
    'mascot_face':{'distance':'850','fov':'12','height':'170','angle':'0'}}

class ExtraScenesSettings:
    def __init__(self, game):
        self.game = Path(game)
        self.path = self.game/'ModCarrerMode/config/extra_scenes.ini'
        self.status_path = self.game/'runtime/extra_scenes_status.ini'

    def document(self):
        doc=configparser.ConfigParser(interpolation=None)
        doc.read_dict(DEFAULTS)
        try:
            if self.path.exists():doc.read_string(self.path.read_text(encoding='utf-8-sig'))
        except (OSError, configparser.Error) as exc:
            raise ValueError('Não foi possível ler as opções de cenas extras.') from exc
        return doc

    def values(self):
        doc=self.document()
        def number(key, default, lo, hi):
            try:value=doc.getint('scenes',key)
            except ValueError:value=default
            return max(lo,min(hi,value))
        return {'enabled':bool(number('enabled',1,0,1)),
                'coach_view':number('coach_view',3,0,3),
                'mascot_view':number('mascot_view',3,0,3),
                'preview_actor':number('preview_actor',0,0,1),
                'test_mode':bool(number('test_mode',0,0,1)),
                'duration_ms':number('duration_ms',5000,1000,10000)}

    def update(self, **values):
        ranges={'enabled':(0,1),'coach_view':(0,3),'mascot_view':(0,3),'preview_actor':(0,1),'test_mode':(0,1)}
        for key,value in values.items():
            if key not in ranges or type(value) is not int or not ranges[key][0]<=value<=ranges[key][1]:
                raise ValueError('Opção de cena inválida.')
        doc=self.document()
        for key,value in values.items():doc['scenes'][key]=str(value)
        self.save(doc)

    def save(self, doc):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp')
        with temporary.open('w',encoding='utf-8',newline='') as out:doc.write(out)
        temporary.replace(self.path)

    def preview(self, actor):
        if type(actor) is not int or actor not in (0,1):raise ValueError('Alvo inválido.')
        doc=self.document()
        try:serial=doc.getint('scenes','preview_serial')
        except ValueError:serial=0
        doc['scenes']['preview_serial']=str(serial%2147483646+1)
        doc['scenes']['preview_actor']=str(actor)
        doc['scenes']['enabled']='1'
        # A disabled actor must be explicitly enabled before requesting its view.
        key='coach_view' if actor==0 else 'mascot_view'
        if self.values()[key]==0:raise ValueError('Escolha uma visão para esse alvo primeiro.')
        self.save(doc)

    def status(self, pid):
        doc=configparser.ConfigParser()
        try:
            doc.read(self.status_path,encoding='utf-8')
            if not pid or doc.getint('runtime','pid')!=pid:return 'Reinicie o FIFA após instalar o mod.'
            if not doc.getboolean('runtime','ready'):return 'Aguardando os personagens da partida.'
            if doc.getboolean('runtime','active'):return 'Cena extra em exibição.'
            if doc.getint('runtime','reason')==4:return 'Sem ângulo frontal seguro; cena original preservada.'
            if doc.get('runtime','mode',fallback='')=='native_muse':return 'Pronto · reação nativa em lateral ou chute para fora.'
            return 'Pronto · cenas originais têm prioridade.'
        except (OSError, ValueError, configparser.Error):return 'Reinicie o FIFA após instalar o mod.'

class ExtraScenesPanel:
    WIDTH, HEIGHT = 600, 490
    def __init__(self, parent, prematch=False):
        self.parent=parent;self.selector=parent.selector;self.focus=0;self.message=''
        self.prematch=prematch
        app=self.selector.app
        self.store=ExtraScenesSettings(getattr(app,'exedir',app.base_dir))
        self._next_tick=0;self._status=None

    def items(self):
        v=self.store.values()
        preview=('Teste durante a partida','Entre em campo e use Cenas extras para solicitar uma tomada.') if self.prematch else ('Testar na próxima parada',('Técnico' if v['preview_actor']==0 else 'Mascote')+' · lateral ou chute para fora')
        return [('Cenas extras',f"Ligadas · até {v['duration_ms']/1000:g} s" if v['enabled'] else 'Desligadas'),
                ('Técnico',VIEWS[v['coach_view']]),('Mascote',VIEWS[v['mascot_view']]),
                preview,('Frequência','Teste · sempre que houver espaço' if v['test_mode'] else 'Normal · exibição ocasional'),
                ('Voltar','Prévia da partida' if self.prematch else 'Ajustes da partida')]

    def targets(self):return [(i,(24,94+i*52,576,136+i*52)) for i in range(6)]

    def activate(self,index,direction=1,adjust=False):
        eligible=(self.selector.app.memory.is_open() and prematch_page(self.selector.app.lastpagename)) if self.prematch else self.selector.match_eligible()
        if not eligible or self.selector.context!=self.selector._context():
            self.selector.close();return
        if index==5:self.parent.back();return
        if index==3 and self.prematch:
            self.message='Opções salvas. O teste de câmera fica disponível em campo.'
            self.selector.render();return
        try:
            v=self.store.values()
            if index==0:self.store.update(enabled=int(not v['enabled']))
            elif index in (1,2):
                key='coach_view' if index==1 else 'mascot_view'
                self.store.update(**{key:(v[key]+direction)%len(VIEWS)})
            elif index==3:
                if adjust:self.store.update(preview_actor=1-v['preview_actor'])
                else:
                    self.store.preview(v['preview_actor'])
                    self.message='Solicitado · lateral ou chute para fora, após cenas originais.'
            elif index==4:self.store.update(test_mode=int(not v['test_mode']))
            if index!=3:self.message='Opção salva; vale para as próximas tomadas.'
        except (OSError,ValueError) as exc:self.message=str(exc)
        self.selector.render()

    def tick(self):
        now=time.monotonic()
        if now<self._next_tick:return
        self._next_tick=now+1
        status='Escolhas salvas para a partida e para as próximas sessões.' if self.prematch else self.store.status(self.selector.app._resolve_fifa_pid())
        if status!=self._status:self._status=status;self.selector.render()

    def handle(self,kind,value):
        if kind==11:self.selector.close();return
        if kind==7:self.parent.back();return
        if kind in (4,5,9):self.focus=(self.focus+(-1 if kind==4 else 1))%6
        elif kind in (2,3):self.activate(self.focus,-1 if kind==2 else 1,adjust=True);return
        elif kind==6:self.activate(self.focus);return
        elif kind==16:
            if 1<=value<=5:self.activate(value-1)
            return
        elif kind in (8,15):
            x,y=value&65535,(value>>16)&65535
            focus=next((i for i,r in self.targets() if r[0]<=x<=r[2] and r[1]<=y<=r[3]),None)
            if focus is None:return
            self.focus=focus
            if kind==8:self.activate(focus);return
        else:return
        self.selector.render()

    def render(self):
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2));draw=OverlayDraw(image)
        draw.rounded_rectangle((0,0,599,489),18,fill='white',outline='#e0e6ee')
        ink,muted='#344651','#728397'
        draw.text((24,22),'Cenas extras',font=self.selector.font(24,True),fill=ink)
        draw.text((24,59),'Tomadas adicionais · rosto ou corpo inteiro',font=self.selector.font(15),fill=muted)
        for (index,rect),(label,detail) in zip(self.targets(),self.items()):
            draw.rounded_rectangle(rect,10,fill='#f4f7fb',outline='#dbe3ed')
            if self.focus==index:draw_focus_ring(draw,rect)
            available=470 if not self.selector.controller_connected else 520
            draw.text((40,rect[1]+5),label,font=self.selector.font(18,True),fill=ink,max_width=available)
            draw.text((40,rect[1]+26),detail,font=self.selector.font(12),fill=muted,max_width=available)
            if not self.selector.controller_connected:
                draw.text((527,rect[1]+15),panel_function_key(index+1) if index<5 else 'Esc',font=self.selector.font(12,True),fill='#0968f8')
        message=self.message or self._status or ('Escolhas salvas para a partida e para as próximas sessões.' if self.prematch else self.store.status(self.selector.app._resolve_fifa_pid()))
        while len(message)>1 and draw.textlength(message,font=self.selector.font(12))>550:message=message[:-2]+'…'
        draw.text((24,414),message,font=self.selector.font(12),fill=muted)
        navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Alterar / testar','Voltar')
        return image
