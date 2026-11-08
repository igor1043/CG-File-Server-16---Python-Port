"""In-game career options, sharing the existing guarded proposal/save service.

The presentation never edits the save. Requests are bound to the live career,
consumed once, and confirmed again by CareerService before any native action.
"""
from datetime import datetime, timedelta
from contextlib import contextmanager,closing
from pathlib import Path
import hashlib, json, secrets, sqlite3, time,math
from .career_transfer_catalog import transfer_catalog


def add_days(day, count):
    return int((datetime.strptime(str(day), '%Y%m%d')+timedelta(days=count)).strftime('%Y%m%d'))


def native_path(value):
    value=str(value)
    if not Path(value).exists():value=value.replace('\\\\','\\')
    if value.startswith('\\\\?\\'):value=value[4:]
    elif value.startswith('\\?\\'):value=value[3:]
    return Path(value).resolve()


def chance(source, target):
    # Reputation is the patch's 0–10 scale; division 1 is the strongest.
    prestige = float(source.get('reputation', 5))-float(target.get('reputation', 5))
    tiers = int(target.get('level', 1))-int(source.get('level', 1))
    return max(5, min(90, math.floor(55+prestige*3.5+tiers*7+.5)))


def require_saved_day(service,today):
    """Do not prepare an offline operation against an older calendar day."""
    from .career_read import CareerRead
    game=Path(getattr(service.app,'exedir',service.app.base_dir))
    save=CareerRead(Path(service.selected['path']).read_bytes(),game/'data/db/fifa_ng_db-meta.xml')
    calendar=save.rows('career_calendar')
    if len(calendar)!=1 or calendar[0].GetIntField('currdate')!=today:
        raise ValueError('Salve a carreira no FIFA antes de confirmar a aposentadoria. Depois volte a esta tela.')


def decide(db, scope, request_id, today, source, target, draw=None):
    """One draw per confirmed request; refusal blocks all clubs in this career."""
    db.execute('CREATE TABLE IF NOT EXISTS career_transfer_requests(scope TEXT,request_id TEXT,game_date INT,target INT,chance INT,accepted INT,next_date INT,PRIMARY KEY(scope,request_id))')
    old = db.execute('SELECT accepted,next_date,chance FROM career_transfer_requests WHERE scope=? AND request_id=?', (scope, request_id)).fetchone()
    if old:return dict(accepted=bool(old[0]), next_date=old[1], chance=old[2], duplicate=True)
    last = db.execute('SELECT MAX(next_date) FROM career_transfer_requests WHERE scope=? AND accepted=0 AND game_date<=?', (scope,today)).fetchone()[0] or 0
    if today < last:raise ValueError('Aguarde até '+str(last)[6:8]+'/'+str(last)[4:6]+'/'+str(last)[:4]+' para fazer outro pedido.')
    probability = chance(source, target);rng = draw or secrets.randbelow
    accepted = rng(100) < probability;next_date = today if accepted else add_days(today, 15+rng(16))
    db.execute('INSERT INTO career_transfer_requests VALUES(?,?,?,?,?,?,?)', (scope, request_id, today, target['id'], probability, int(accepted), next_date))
    return dict(accepted=accepted, next_date=next_date, chance=probability, duplicate=False)


class CareerOptions:
    def __init__(self, service):
        self.service=service;self.game=Path(getattr(service.app,'exedir',service.app.base_dir))
        self.root=self.game/'ModCarrerMode/runtime/career_options';self.root.mkdir(parents=True,exist_ok=True)
        self.token='';self.scope='';self.identity=None;self.next_tick=0;self.message='';self.teams={};self.next_date=0;self.signature=None;self.snapshot=None;self.snapshot_version=None;self.labels_version=None;self.country_labels={};self.league_labels={}

    @staticmethod
    def clean(value):return str(value).replace('\t',' ').replace('\r',' ').replace('\n',' ')

    @contextmanager
    def connection(self):
        # Keep the requests beside this save's existing financial sidecar.
        db=sqlite3.connect(Path(self.service.selected['path']).parent/'server16_loans.sqlite3',timeout=2)
        try:
            with db:yield db
        finally:db.close()

    def current(self):
        svc=self.service
        if not svc.inspection or not svc.selected:return None
        context=svc.inspection['context'];profile=svc.context_reader.profile(fresh=True)
        if not profile or context.get('player_id') is not None or any(profile.get(k)!=context[k] for k in ('userid','club_id')):return None
        path=self.game/'ModCarrerMode/runtime/career_fce_snapshot.json'
        try:
            stat=path.stat();version=(stat.st_size,stat.st_mtime_ns)
            if version!=self.snapshot_version:self.snapshot=json.loads(path.read_text(encoding='utf8'));self.snapshot_version=version
            snapshot=self.snapshot
        except (OSError,ValueError):return None
        pid=int(getattr(svc.app.memory,'process_id',0));epoch=profile.get('context_epoch')
        if snapshot.get('pid')!=pid or snapshot.get('club')!=context['club_id'] or snapshot.get('fceContextEpoch')!=epoch:return None
        today=int(snapshot.get('date',0))
        try:datetime.strptime(str(today),'%Y%m%d')
        except ValueError:return None
        # Career lineage survives normal saves/reloads and separates a new
        # career which later reuses the same slot and userid.
        try:
            state=json.loads((self.game/'ModCarrerMode/runtime/manager_market/state_ready.json').read_text(encoding='utf8'))
            if state['pid']!=pid or state['epoch']!=epoch or state['club']!=context['club_id'] or native_path(state['save'])!=native_path(svc.selected['path']):return None
            with closing(sqlite3.connect(native_path(state['database']).as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
                lineage=db.execute('SELECT career FROM branches WHERE id=?',(state['branch'],)).fetchone()
                if not lineage:return None
            scope=hashlib.sha256((lineage[0]+'|'+str(context['userid'])).encode()).hexdigest()
        except (OSError,ValueError,KeyError,sqlite3.Error):return None
        return context,profile,pid,epoch,today,scope

    def tick(self):
        if time.monotonic()<self.next_tick:return
        svc=self.service;page=svc.live_page()
        self.next_tick=time.monotonic()+(.3 if '/server16/career' in page.casefold() else 2)
        current=self.current() if svc.in_career(svc.live_page()) else None
        if not current:
            self.identity=None;self.token='';self.publish(0,0,0,0,False,[],[],[], 'Abra uma carreira de treinador e aguarde a leitura do save.');return
        context,profile,pid,epoch,today,scope=current
        identity=(scope,pid,epoch,context['club_id'])
        if identity!=self.identity:self.identity=identity;self.token=secrets.token_hex(16);self.scope=scope;self.message='';self.next_date=0
        data=transfer_catalog(svc.inspection['catalog'],svc.catalog);leagues={v['id']:v for v in data['leagues']};teams={v['id']:dict(v,reputation=5,level=1) for v in data['teams']}
        for league,team in data['links']:
            if team in teams:teams[team].update(league=league,level=leagues[league]['level'])
        if context['club_id'] not in teams:
            source=next((v for v in svc.inspection['catalog']['teams'] if v['id']==context['club_id']),None)
            if source:
                source_league=next((lid for lid,tid in svc.inspection['catalog']['links'] if tid==source['id']),0)
                level=next((v['level'] for v in svc.inspection['catalog']['leagues'] if v['id']==source_league),1)
                teams[source['id']]=dict(source,reputation=5,league=source_league,level=level)
        # Use the same world catalogue as the manager market, scoped to this
        # exact game process/career. The save remains the membership authority.
        try:
            state=json.loads((self.game/'ModCarrerMode/runtime/manager_market/state_ready.json').read_text(encoding='utf8'))
            if state['pid']==pid and state['club']==context['club_id'] and native_path(state['save'])==native_path(svc.selected['path']):
                uri=native_path(state['database']).as_uri()+'?mode=ro'
                with closing(sqlite3.connect(uri,uri=True,timeout=1)) as db:
                    for club,rep in db.execute('SELECT club_id,reputation FROM clubs WHERE branch=?',(state['branch'],)):
                        if club in teams:teams[club]['reputation']=float(rep)
        except (OSError,ValueError,KeyError,sqlite3.Error):pass
        self.teams=teams
        request=self.root/'request.tsv'
        if request.exists():
            try:
                row=request.read_text(encoding='utf8').strip().split('\t');request.unlink()
                if len(row)!=5 or row[0]!=self.token:raise ValueError('Pedido expirado. Reabra a tela e confirme novamente.')
                _,ident,action,team,league=row
                if action=='transfer':
                    target=teams.get(int(team));source=teams.get(context['club_id'])
                    if not source or not target or target.get('league')!=int(league) or target['id']==source['id']:raise ValueError('Selecione outro clube válido.')
                    if svc.pending or svc.busy:raise ValueError('Aguarde a conclusão do pedido em andamento.')
                    # Readiness is verified before drawing; a failed provider is
                    # not treated as a club refusal and cannot start a cooldown.
                    svc.require_active(allow_live=True);svc.jobs_runtime.ensure()
                    if not svc.jobs_runtime.ready():raise ValueError(svc.jobs_runtime.error or 'A integração de propostas está sendo preparada.')
                    with self.connection() as db:decision=decide(db,scope,ident,today,source,target)
                    if decision['duplicate']:raise ValueError('Este pedido já foi processado.')
                    self.next_date=decision['next_date']
                    if decision['accepted']:
                        svc.confirm('transfer',team_id=target['id'],league_id=int(league));self.message='Pedido aceito. Volte à Central para abrir a proposta do FIFA.'
                    else:
                        date=str(self.next_date);self.message='O clube recusou o pedido. Tente novamente em '+date[6:8]+'/'+date[4:6]+'/'+date[:4]+'.'
                        svc.notify('transfer_declined',self.message,dict(request_id=ident))
                elif action in ('remove_retirement','remove_and_rejuvenate'):
                    svc.confirm(action);self.message=''
                else:raise ValueError('Opção desconhecida.')
            except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as exc:self.message=str(exc);svc.notify('options_error',self.message,dict(request_id=secrets.token_hex(8)))
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS career_transfer_requests(scope TEXT,request_id TEXT,game_date INT,target INT,chance INT,accepted INT,next_date INT,PRIMARY KEY(scope,request_id))')
            self.next_date=db.execute('SELECT MAX(next_date) FROM career_transfer_requests WHERE scope=? AND accepted=0 AND game_date<=?',(scope,today)).fetchone()[0] or 0
        nations=(svc.catalog or {}).get('nations',data['nations']);nations=[dict(id=k,name=v) for k,v in nations.items()] if isinstance(nations,dict) else nations
        self.publish(pid,epoch,today,context['club_id'],not svc.busy and not svc.pending,nations,list(leagues.values()),list(teams.values()),self.message or svc.message)

    def publish(self,pid,epoch,today,club,ready,nations,leagues,teams,message):
        catalog=self.game/'ModCarrerMode/data/manager_market/catalog.sqlite3'
        try:
            stat=catalog.stat();version=(stat.st_size,stat.st_mtime_ns)
            if self.labels_version!=version:
                with closing(sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
                    self.country_labels=dict(db.execute('SELECT nation_id,name FROM country_catalog'))
                    self.league_labels=dict(db.execute('SELECT league_id,name FROM league_catalog'))
                self.labels_version=version
        except (OSError,sqlite3.Error):pass
        from .career_service import retirement_age
        rows=[['O',1,pid,epoch,self.token,int(ready),today,self.next_date,club,message,retirement_age(self.game)]]
        rows += [['N',r['id'],self.country_labels.get(int(r['id']),r.get('name',''))] for r in nations]
        rows += [['L',r['id'],r['country_id'],r['level'],self.league_labels.get(r['id'],r['name'])] for r in leagues]
        rows += [['T',r['id'],r.get('league',0),r['reputation'],r['level'],r['name']] for r in teams]
        raw='\n'.join('\t'.join(map(self.clean,row)) for row in rows)+'\n'
        signature=hashlib.sha256(raw.encode()).hexdigest()
        if signature==self.signature:return
        target=self.root/'view.tsv';temporary=target.with_suffix('.new');temporary.write_text(raw,encoding='utf8');temporary.replace(target);self.signature=signature
