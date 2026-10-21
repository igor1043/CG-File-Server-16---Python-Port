"""A dedicated career overlay on the shared native texture/input transport."""
from __future__ import annotations

import time
from PIL import Image

from .career_save_worker import MAX_MONEY
from .input_hints import navigation_hint, footer_y
from .overlay_canvas import OverlayDraw, draw_focus_ring
from .career_artwork import artwork
from .career_service import retirement_age
from .career_transfer_catalog import transfer_catalog


def money(value):
    return f'{value:,}'.replace(',', '.')


class CareerPanel:
    WIDTH, HEIGHT = 600, 680

    def __init__(self, selector, service):
        self.selector, self.service = selector, service
        self.page = 'status' if service.pending or service.state == 'done' else 'home'
        self.focus = 0
        self.message = ''
        self.amount = ''
        self.country = self.league = self.team = None
        self._filters_touched = False
        self._bound_generation = None
        self.confirmation = None
        self.target_age = retirement_age(getattr(selector.app, 'exedir', selector.app.base_dir))
        self._revision = -1
        self._loading_signature = None
        self._next_loading_frame = 0
        self._transfer_source = self._transfer_reference = self._transfer_data = None
        if service.catalog is None and not service.pending:
            service.load()

    def tick(self):
        if (self.page=='confirm' and self.confirmation
                and self.confirmation.get('generation') != self.service.generation):
            self.page=('home' if (self.service.inspection or {}).get('save_synced') is False
                       else self.confirmation.get('return','home'))
            self.confirmation=None
            self.focus=0
            self.message='A carreira foi atualizada. Revise o pedido.'
        gate=self.data_gate()
        signature=(gate,self.service.state,self.service.busy,self.service.generation)
        now=time.monotonic()
        if (self._revision != self.service.revision or signature != self._loading_signature
                or (gate=='loading' and now>=self._next_loading_frame)):
            self._revision = self.service.revision
            self._loading_signature=signature
            self._next_loading_frame=now+.2
            self.focus = min(self.focus, max(0,len(self.items())-1))
            self.selector.render()

    def data_gate(self):
        """Reveal a complete, inspected career together; never show partial lists."""
        svc=self.service
        if self.page=='status' or svc.pending:
            return None
        ready=(svc.catalog is not None and svc.selected and svc.inspection
               and svc.inspection.get('context') and svc.inspection.get('catalog'))
        if ready and not svc.busy:
            return None
        if svc.state=='waiting_save':return 'save'
        return 'error' if svc.state=='error' else 'loading'

    def data(self):
        inspection = self.service.inspection
        data = inspection.get('catalog') if inspection else self.service.catalog
        if not data:return {'nations':{}, 'leagues':[], 'teams':[], 'links':[]}
        reference=self.service.catalog
        if data is not self._transfer_source or reference is not self._transfer_reference:
            self._transfer_data=transfer_catalog(data,reference)
            self._transfer_source,self._transfer_reference=data,reference
        return self._transfer_data

    def countries(self):
        data = self.data()
        active = {league for league, team in data['links']}
        ids = {r['country_id'] for r in data['leagues'] if r['id'] in active}
        nations = (self.service.catalog or {}).get('nations', {})
        return sorted([(ident, nations.get(str(ident), f'Região {ident}')) for ident in ids], key=lambda r:r[1].casefold())

    def leagues(self):
        active = {league for league, team in self.data()['links']}
        return sorted([r for r in self.data()['leagues'] if r['country_id']==self.country and r['id'] in active],
                      key=lambda r:(r['level'],r['name'].casefold(),r['id']))

    def teams(self):
        ids = {team for league,team in self.data()['links'] if league==self.league}
        return sorted([r for r in self.data()['teams'] if r['id'] in ids], key=lambda r:(r['name'].casefold(),r['id']))

    def reset_filters(self):
        if self.service.inspection and self._bound_generation != self.service.generation:
            self._bound_generation = self.service.generation
            if not self._filters_touched:
                current = self.service.inspection['context']['club_id']
                leagues = {league for league,team in self.data()['links'] if team==current}
                rows = [row for row in self.data()['leagues'] if row['id'] in leagues]
                if len(rows)==1:
                    self.country,self.league,self.team=rows[0]['country_id'],rows[0]['id'],current
        countries = self.countries()
        if self.country not in {r[0] for r in countries}:
            self.country = countries[0][0] if countries else None
        leagues = self.leagues()
        if self.league not in {r['id'] for r in leagues}:
            self.league = leagues[0]['id'] if leagues else None
        teams = self.teams()
        if self.team not in {r['id'] for r in teams}:
            self.team = teams[0]['id'] if teams else None

    def items(self):
        svc = self.service
        if self.data_gate():
            return [('Fechar','Voltar ao FIFA')]
        if self.page == 'home':
            return [('Transferir para outro clube','Escolha país / região, divisão e clube'),
                    ('Finanças','Solicitar verba para transferências'),
                    ('Aposentadoria','Remover aposentadoria ou rejuvenescer'),
                    ('Estádio de fundo','Trocar o cenário 3D do clube da carreira'), ('Fechar','Voltar ao FIFA')]
        if self.page == 'retirement':
            return [('Remover aposentadoria','Manter a idade dos jogadores'),
                    ('Remover e rejuvenescer',f'Jogadores em aposentadoria voltam a ter {self.target_age} anos'),
                    ('Voltar','Modo carreira')]
        if self.page == 'clubs':
            self.reset_filters()
            country = next((r[1] for r in self.countries() if r[0]==self.country),'Indisponível')
            league = next((r['name'] for r in self.leagues() if r['id']==self.league),'Indisponível')
            team = next((r['name'] for r in self.teams() if r['id']==self.team),'Indisponível')
            return [('País / região',country),('Liga / divisão',league),('Time',team),
                    ('Pedir transferência','Revisar o clube escolhido'),('Voltar','Modo carreira')]
        if self.page == 'finances':
            context = (svc.inspection or {}).get('context',{})
            detail = ('Salve a carreira para ler o orçamento do novo clube'
                      if svc.inspection and svc.inspection.get('save_synced') is False else
                      'Orçamento atual: '+money(context['budget']) if context else 'Lendo a carreira em execução…')
            return [('Solicitar verba',detail),('Voltar','Modo carreira')]
        if self.page == 'funds':
            return [(key,'') for key in ('1','2','3','4','5','6','7','8','9','Limpar','0','Apagar')] + [
                ('Solicitar '+money(int(self.amount or '0')),'Revisar pedido de verba'),('Voltar','Finanças')]
        if self.page == 'confirm':
            live=(self.confirmation or {}).get('action')=='transfer' and (svc.inspection or {}).get('context',{}).get('player_id') is None
            return [('Confirmar pedido','Substituir o pedido anterior pelo clube escolhido' if live else 'Aplicar depois de sair da carreira'),('Voltar','Revisar a escolha')]
        if svc.pending and svc.pending.get('action')=='live_job':
            return [('Fechar','Aguarde a confirmação do FIFA')]
        if svc.pending:
            return [('Cancelar pedido','Manter o save atual'),('Fechar','Acompanhe ao voltar ao menu principal')]
        return [('Voltar','Modo carreira'),('Fechar','Voltar ao FIFA')]

    def targets(self):
        count = len(self.items())
        if self.data_gate():
            return [(0,(24,500,576,558))]
        if self.page == 'clubs':
            return [(i,(24,110+i*128,576,220+i*128)) for i in range(3)] + [
                (3,(24,500,576,550)),(4,(24,562,576,600))]
        if self.page == 'funds':
            return [(i,(24+(i%3)*190,192+(i//3)*65,196+(i%3)*190,247+(i//3)*65)) for i in range(12)] + [
                (12,(24,470,576,520)),(13,(24,535,576,590))]
        if self.page in ('confirm','status'):
            return [(i,(24,430+i*72,576,490+i*72)) for i in range(count)]
        pitch = 72
        return [(i,(24,110+i*pitch,576,168+i*pitch)) for i in range(count)]

    def back(self):
        if self.data_gate():
            self.selector.close()
            return
        destination = {'home':None,'clubs':'home','finances':'home','retirement':'home',
                       'funds':'finances','confirm':self.confirmation['return'] if self.confirmation else 'home',
                       'status':'home'}[self.page]
        if destination is None:
            self.selector.close()
            return
        self.page, self.focus, self.message = destination, 0, ''
        self.selector.render()

    def require_save(self, allow_live=False):
        self.service.require_active(allow_live=allow_live)

    def activate(self, index, direction=1):
        svc = self.service
        if self.data_gate():
            self.selector.close()
            return
        try:
            if self.page == 'home':
                if index in (0,1,2):
                    if svc.pending:
                        self.page='status'
                    else:
                        self.page=('clubs','finances','retirement')[index]
                elif index==3:
                    self.selector.open(frontend=True,career=True);return
                else:
                    self.selector.close();return
                self.focus=0
            elif self.page == 'retirement':
                if index in (0,1):
                    self.require_save()
                    self.confirmation={'action':('remove_retirement','remove_and_rejuvenate')[index],
                        'return':'retirement', 'label':('Manter as idades',f'Rejuvenescer para {self.target_age} anos')[index],
                        'generation':svc.generation}
                    self.page='confirm';self.focus=1
                else:self.back();return
            elif self.page == 'clubs':
                if index<3:
                    self.reset_filters()
                    self._filters_touched=True
                    options = (self.countries() if index==0 else
                               [(r['id'],r['name']) for r in self.leagues()] if index==1 else
                               [(r['id'],r['name']) for r in self.teams()])
                    if options:
                        field=('country','league','team')[index]
                        current=next((i for i,r in enumerate(options) if r[0]==getattr(self,field)),0)
                        setattr(self,field,options[(current+direction)%len(options)][0])
                        self.reset_filters()
                elif index==3:
                    self.require_save(allow_live=(svc.inspection or {}).get('context',{}).get('player_id') is None)
                    team=next((r for r in self.teams() if r['id']==self.team),None)
                    if not team:raise ValueError('Não há clube disponível nesta seleção.')
                    if team['id']==svc.inspection['context']['club_id']:raise ValueError('Você já está nesse clube.')
                    self.confirmation={'action':'transfer','return':'clubs','team_id':team['id'],
                                       'league_id':self.league,'label':team['name'],'generation':svc.generation}
                    self.page='confirm';self.focus=1
                else:self.back();return
            elif self.page == 'finances':
                if index==0:
                    self.require_save()
                    context=(svc.inspection or {}).get('context',{})
                    if context.get('player_id') is not None:
                        raise ValueError('Solicitação de verba disponível na carreira de treinador.')
                    self.page='funds';self.focus=0
                else:self.back();return
            elif self.page == 'funds':
                if index<12:
                    self.digit(self.items()[index][0])
                elif index==12:
                    self.require_save()
                    amount=int(self.amount or '0')
                    if not 0<amount<=MAX_MONEY:raise ValueError('Informe uma verba entre 1 e 2 bilhões.')
                    self.confirmation={'action':'funds','return':'funds','amount':amount,
                                       'label':money(amount),'generation':svc.generation}
                    self.page='confirm';self.focus=1
                else:self.back();return
            elif self.page == 'confirm':
                if index==0:
                    if self.confirmation.get('generation') != svc.generation:
                        self.page=self.confirmation['return'];self.focus=0
                        raise ValueError('A carreira foi atualizada. Revise o pedido antes de confirmar.')
                    values={k:v for k,v in self.confirmation.items() if k not in ('action','return','label','generation')}
                    svc.confirm(self.confirmation['action'],**values)
                    self.page='status';self.focus=1
                    self.selector.close()
                    return
                else:self.back();return
            elif self.page == 'status':
                if svc.pending and svc.pending.get('action')=='live_job':
                    self.selector.close();return
                if index==0:
                    if svc.pending:svc.cancel()
                    self.page='home';self.focus=0
                else:self.selector.close();return
            self.message=''
        except (OSError,RuntimeError,ValueError,KeyError) as exc:
            self.message=str(exc)
        self.selector.render()

    def digit(self,key):
        if key=='Apagar':self.amount=self.amount[:-1]
        elif key=='Limpar':self.amount=''
        elif key.isdigit() and len(key)==1:
            candidate=(self.amount+key).lstrip('0')
            if int(candidate or '0')<=MAX_MONEY:self.amount=candidate
            else:self.message='Limite de 2 bilhões por pedido.'

    def handle(self,kind,value):
        if kind==11:self.selector.close();return
        if kind==7:self.back();return
        if self.data_gate():
            if kind==6 or (kind==16 and value in (1,2)):
                self.selector.close()
            elif kind==8:
                x,y=value&65535,(value>>16)&65535
                if any(r[0]<=x<=r[2] and r[1]<=y<=r[3] for _,r in self.targets()):
                    self.selector.close()
            return
        if kind==10 and self.page=='funds':
            if value==8:self.digit('Apagar')
            elif 48<=value<=57:self.digit(chr(value))
            else:return
            self.selector.render();return
        if kind==16:
            if value==2:self.back()
            elif value==1:
                action={'home':0,'clubs':3,'finances':0,'retirement':self.focus,'funds':12,'confirm':0}.get(self.page)
                if action is not None:self.activate(action)
            return
        if kind in (8,15):
            x,y=value&65535,(value>>16)&65535
            index=next((i for i,r in self.targets() if r[0]<=x<=r[2] and r[1]<=y<=r[3]),None)
            if index is None:return
            self.focus=index
            if kind==8:
                self.activate(index,-1 if self.page=='clubs' and index<3 and x<80 else 1)
                return
        elif kind==6:self.activate(self.focus);return
        elif kind in (2,3) and self.page=='clubs' and self.focus<3:
            self.activate(self.focus,-1 if kind==2 else 1);return
        elif kind in (2,3,4,5,9):
            if self.page=='funds' and self.focus<12 and kind in (2,3,4,5):
                change={2:-1,3:1,4:-3,5:3}[kind]
            else:change=-1 if kind in (2,4) else 1
            self.focus=(self.focus+change)%len(self.items())
        else:return
        self.selector.render()

    def render(self):
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2))
        draw=OverlayDraw(image)
        draw.rounded_rectangle((0,0,599,self.HEIGHT-1),18,fill='white',outline='#dbe3ed')
        ink,muted,blue='#344651','#728397','#0968f8'
        def text(x,y,value,size=15,color=ink,bold=False,width=552):
            value=str(value)
            while len(value)>1 and draw.textlength(value,font=self.selector.font(size,bold))>width:
                value=value[:-2]+'…'
            draw.text((x,y),value,font=self.selector.font(size,bold),fill=color)
        gate=self.data_gate()
        if gate:
            text(24,22,'Modo carreira',25,bold=True)
            text(24,63,'Preparando suas opções',14,muted)
            if gate=='loading':
                draw.ellipse((267,168,333,234),outline='#e7effc',width=6)
                angle=(time.monotonic()*220)%360
                draw.arc((267,168,333,234),angle,angle+100,fill=blue,width=6)
                text(24,270,'Carregando dados da carreira…',23,bold=True)
                text(24,312,'Aguarde. As opções aparecerão quando tudo estiver pronto.',14,muted)
                stage=0 if self.service.catalog is None else 1 if not self.service.selected else 2
                labels=('Clubes e competições','Carreira em execução','Dados do save')
                for index,label in enumerate(labels):
                    x=24+index*188
                    color=blue if index<=stage else '#e1e7ee'
                    draw.rounded_rectangle((x,367,x+172,372),2,fill=color)
                    text(x,385,label,11,blue if index==stage else muted,width=176)
            elif gate=='save':
                text(24,260,'Salve o progresso no FIFA.',22,bold=True)
                text(24,306,'O painel atualizará os dados automaticamente após salvar.',14,muted)
            else:
                text(24,260,'Não foi possível carregar a carreira.',22,bold=True)
                text(24,306,'Feche e abra o painel para tentar novamente.',14,muted)
            words=(self.service.message or '').split();lines=['']
            for word in words:
                candidate=(lines[-1]+' '+word).strip()
                if draw.textlength(candidate,font=self.selector.font(13))>552 and lines[-1]:lines.append(word)
                else:lines[-1]=candidate
            for i,line in enumerate(lines[:3]):text(24,425+i*20,line,13,muted)
            rect=self.targets()[0][1]
            draw.rounded_rectangle(rect,10,fill='#f4f7fb',outline='#dbe3ed')
            draw_focus_ring(draw,rect)
            text(40,rect[1]+17,'Fechar',17,bold=True)
            navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Fechar','Fechar')
            return image
        title={'home':'Modo carreira','clubs':'Transferir para outro clube',
               'finances':'Finanças','funds':'Solicitar verba','retirement':'Aposentadoria',
               'confirm':'Confirmar pedido','status':'Pedido da carreira'}[self.page]
        text(24,22,title,25,bold=True)
        context=(self.service.inspection or {}).get('context')
        caption=(context['club']+' · '+('Jogador' if context['player_id'] is not None else 'Treinador')) if context else 'Suas opções para a carreira'
        text(24,63,caption,14,muted)
        for (index,rect),(label,detail) in zip(self.targets(),self.items()):
            draw.rounded_rectangle(rect,10,fill='#f4f7fb',outline='#dbe3ed')
            if self.focus==index:draw_focus_ring(draw,rect)
            if self.page=='clubs' and index<3:
                y=rect[1]
                text(164,y+16,label.upper(),11,muted,True,width=344)
                text(164,y+39,detail,21,ink,True,width=344)
                options=(self.countries(),[(r['id'],r['name']) for r in self.leagues()],
                         [(r['id'],r['name']) for r in self.teams()])[index]
                selected=(self.country,self.league,self.team)[index]
                position=next((i+1 for i,row in enumerate(options) if row[0]==selected),0)
                text(164,y+77,f'{position} de {len(options)}',11,muted,width=330)
                for x,direction in ((36,-1),(528,1)):
                    draw.rounded_rectangle((x,y+32,x+36,y+78),9,fill='#e7effc')
                    cx,cy=x+18,y+55
                    draw.line([(cx-direction*4,cy-7),(cx+direction*4,cy),(cx-direction*4,cy+7)],fill=blue,width=2)
                data=dict(self.data())
                data.update({key:(self.service.catalog or {}).get(key,{}) for key in ('nations','nation_codes')})
                game=getattr(self.selector.app,'exedir',self.selector.app.base_dir)
                icon=artwork(game,('country','league','team')[index],selected,data,(144,144))
                if icon:
                    image.alpha_composite(icon,(112*2-icon.width//2,(y+55)*2-icon.height//2))
                else:
                    # Keep the artwork position visible when an optional pack is missing.
                    draw.rounded_rectangle((78,y+35,132,y+77),8,fill='#e1e7ee')
                    text(85,y+44,('PAÍS','LIGA','TIME')[index],10,muted,True,width=48)
            elif self.page=='funds' and index<12:
                text(rect[0]+15,rect[1]+14,label,20,bold=True,width=145)
            else:
                width=rect[2]-rect[0]-32
                text(rect[0]+16,rect[1]+9,label,17,bold=True,width=width)
                if detail and rect[3]-rect[1]>42:text(rect[0]+16,rect[1]+33,detail,12,muted,width=width)
        if self.page=='home':
            text(24,408,'Carreira em execução',15,bold=True)
            text(24,434,self.service.selected['title'] if self.service.selected else 'Identificação automática em andamento…',13,muted)
            text(24,460,'Clubes: proposta para você aceitar pelo FIFA.',14,bold=True)
            text(24,486,'Finanças e aposentadoria: salve antes do pedido.',14,muted)
            text(24,512,'Essas alterações são aplicadas após sair da carreira.',13,muted)
        elif self.page=='retirement':
            text(24,370,'As duas opções afetam jogadores marcados para se aposentar.',13,muted)
            text(24,400,'Salve seu progresso antes de confirmar o pedido.',14,bold=True)
            text(24,430,'Depois, saia da carreira sem salvar novamente.',14,muted)
            text(24,460,'Aguarde a confirmação visual e sonora para reabrir.',14,muted)
        elif self.page=='funds':
            text(24,115,'Verba adicional solicitada',14,muted)
            text(24,141,money(int(self.amount or '0')),29,blue,True)
        elif self.page=='confirm':
            request=self.confirmation or {}
            manager_offer=request.get('action')=='transfer' and (context or {}).get('player_id') is None
            retirement=request.get('action') in ('remove_retirement','remove_and_rejuvenate')
            text(24,130,'Remover aposentadoria:' if retirement else
                 ('Solicitar proposta de:' if manager_offer else 'Transferir para:') if request.get('action')=='transfer'
                 else 'Adicionar ao orçamento:',18,bold=True)
            text(24,170,request.get('label',''),27,blue,True)
            if request.get('action')=='funds' and context and context.get('budget') is not None:
                text(24,218,'Novo orçamento: '+money(context['budget']+request['amount']),17)
            text(24,280,'1. Confirme o pedido.',16)
            text(24,310,'2. Feche o painel e fique na Central da Carreira.' if manager_offer else '2. Saia da carreira sem salvar novamente.',16)
            text(24,340,'3. Aguarde a tela de contratação do próprio FIFA.' if manager_offer else '3. Aguarde a aplicação no menu principal.',16)
            text(24,370,'4. Nessa tela, você escolhe aceitar ou recusar.' if manager_offer else '4. Carregue este mesmo save.',16)
            if manager_offer:text(24,410,'Este pedido substitui a proposta ou candidatura anterior.',13,muted)
        elif self.page=='status':
            if (self.service.pending or {}).get('action')=='live_job':
                text(24,145,'Aguardando confirmação do FIFA',25,blue,True)
                text(24,210,'Feche o painel e fique na Central da Carreira.',16)
                text(24,243,'Aguarde a abertura do contrato, sem avançar a data.',14,muted)
                text(24,300,'A espera é em tempo real, com a carreira aberta.',14,muted)
                navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Fechar','Voltar')
                return image
            action=(self.service.pending or {}).get('action')
            title=('Aposentadoria solicitada' if action in ('remove_retirement','remove_and_rejuvenate') else
                   'Verba solicitada' if action=='funds' else 'Transferência solicitada')
            if self.service.state=='done':title='Pedido aplicado'
            if self.service.state=='error':title='Pedido não aplicado'
            if self.service.state=='applying':title='Aplicando o pedido'
            text(24,145,title,25,blue,True)
            if self.service.state=='done':
                text(24,210,'A alteração foi concluída nesta carreira.',16)
                text(24,243,'Agora carregue novamente esta carreira.',14,muted)
            elif self.service.state=='applying':
                text(24,210,'Aguarde no menu principal.',16)
                text(24,243,'Carregue a carreira depois da confirmação.',14,muted)
            elif self.service.state=='error':
                text(24,210,'Confira o motivo abaixo e refaça o pedido.',16)
                text(24,243,'A carreira será reconhecida automaticamente.',14,muted)
            else:
                text(24,210,'Saia da carreira e aguarde no menu principal.',16)
                text(24,243,'Carregue novamente após a confirmação de aplicação.',14,muted)
            text(24,300,'Uma cópia do save é guardada antes da alteração.',13,muted)
        message=self.message or self.service.message
        # Wrap status; do not hide the reason for a rejected save operation.
        words=message.split();lines=['']
        for word in words:
            candidate=(lines[-1]+' '+word).strip()
            if draw.textlength(candidate,font=self.selector.font(12))>550 and lines[-1]:lines.append(word)
            else:lines[-1]=candidate
        for i,line in enumerate(lines[:2]):text(24,605+i*16,line,12,muted)
        navigation_hint(draw,self.selector,footer_y(self.HEIGHT),'Selecionar','Voltar')
        return image
