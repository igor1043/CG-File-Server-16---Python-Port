"""Career overlay jobs, read-only discovery, and guarded offline publication."""
from __future__ import annotations

import ctypes
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .career_save_worker import MAX_MONEY, blocks, fingerprint, stage_job_offer, read_job_offer
from .fifa_db import _find_dll, _find_python32, _find_worker, _no_window_flag
from .shutdown import run_owned_reader
from .career_context import CareerContext
from .career_active_save import read_active_save, version, ActiveCareerUnavailable
from .career_feedback import CareerFeedback
from .career_jobs_runtime import CareerJobsRuntime
from .career_read import read as read_career
from .career_transfer_catalog import transfer_catalog


def career_page(page):
    page = (page or '').lower().replace('\\', '/')
    return '/career/' in page and not any(token in page for token in (
        'prematch', 'kitselect', 'kit_select', 'sideselect', 'teamselect',
        'newcareer', 'createcareer', 'loadcareer', 'careersetup'))


def safe_exit_page(page):
    page = (page or '').lower().replace('\\', '/')
    return bool(page and not career_page(page) and any(token in page for token in (
        '/mainmenu', '/main_menu', '/mainhub', '/frontend/hub', '/frontend/main')))


def discover_saves():
    """Look only in FIFA's save roots, never select the newest file implicitly."""
    roots = [Path.home()/'Documents', Path.home()/'Documentos']
    for env in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        if os.environ.get(env):
            roots += [Path(os.environ[env])/'Documents', Path(os.environ[env])/'Documentos']
    if os.name == 'nt':
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            roots.insert(0, Path(buffer.value))
    saves = {}
    for documents in roots:
        root = documents/'FIFA 16'
        if not root.is_dir():
            continue
        for path in root.glob('*/FIFA16/*/DATA'):
            try:
                with path.open('rb') as stream:
                    header = stream.read(160)
                if (len(header) != 160 or int.from_bytes(header[136:140], 'little') != 56
                        or header[116:132].split(b'\0',1)[0] != b'SaveType_Career'):
                    continue
                title = header[16:80].split(b'\0',1)[0].decode('utf-8', errors='replace').strip()
                canonical = str(path.resolve())
                saves[canonical] = {'path': canonical, 'title': title or path.parent.name,
                                    'slot': path.parent.name, 'modified': path.stat().st_mtime}
            except OSError:
                continue
    return sorted(saves.values(), key=lambda row: (-row['modified'], row['path']))


def run_worker(game, request):
    python, dll, worker = _find_python32(), _find_dll(), _find_worker('career_save_worker.py')
    if not all((python, dll, worker)):
        raise RuntimeError('Ponte de edição de saves indisponível. Atualize o Server16.')
    with tempfile.TemporaryDirectory(prefix='server16-request-') as temporary:
        path = Path(temporary)/'request.json'
        path.write_text(json.dumps(dict(request, game=str(game), dll=str(dll.resolve()))), encoding='utf-8')
        env = dict(os.environ, PYTHONNOUSERSITE='1')
        result = run_owned_reader([str(python), str(worker), str(path)], capture_output=True,
                                  text=True, encoding='utf-8', errors='replace', env=env,
                                  creationflags=_no_window_flag(), timeout=90)
        try:
            payload = json.loads(result.stdout or '{}')
        except ValueError:
            raise RuntimeError('Resposta inválida da ponte de saves.') from None
        if result.returncode or not payload.get('ok'):
            raise RuntimeError(payload.get('error') or 'Falha ao processar o save.')
        return payload


def retirement_age(game):
    path = Path(game)/'ModCarrerMode/config/career_retirement_background.ini'
    try:
        values = dict(line.split('=', 1) for line in path.read_text(encoding='utf-8-sig').splitlines()
                      if '=' in line and not line.lstrip().startswith((';', '#')))
        age = int(values.get('target_age', 18))
        return age if 12 <= age <= 50 else 18
    except (OSError, ValueError):
        return 18


def publish_save(path, original_hash, payload, backup_root):
    """Back up both files; publish DATA under an exclusive Windows file lock.

    This save format's INDEX records lengths and labels, not payload checksums.
    Fixed block sizes keep all INDEX offsets valid; only DATA's CRC changes.
    """
    path = Path(path).resolve()
    if path.name != 'DATA' or not (path.parent/'INDEX').is_file():
        raise ValueError('Contêiner DATA/INDEX não encontrado.')
    blocks(payload)
    before = path.read_bytes()
    if fingerprint(before) != original_hash or len(before) != len(payload):
        raise ValueError('O save mudou antes de aplicar. Faça o pedido novamente.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    backup = Path(backup_root)/(path.parent.name+'_'+stamp)
    backup.mkdir(parents=True, exist_ok=False)
    (backup/'DATA').write_bytes(before)
    shutil.copy2(path.parent/'INDEX', backup/'INDEX')
    (backup/'receipt.json').write_text(json.dumps({
        'source': str(path), 'before': original_hash, 'after': fingerprint(payload),
        'created_utc': stamp}, indent=2), encoding='utf-8')
    if os.name == 'nt':
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                      ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.CreateFileW(str(path), 0xC0000000, 0, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), 'O save está ocupado. Aguarde no menu principal.')
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except Exception:
            kernel.CloseHandle(handle)
            raise
        stream = os.fdopen(descriptor, 'r+b')
    else:
        stream = path.open('r+b')
    with stream:
        actual = stream.read()
        if fingerprint(actual) != original_hash:
            raise ValueError('O save mudou enquanto a alteração era preparada.')
        try:
            stream.seek(0)
            if stream.write(payload) != len(payload):
                raise OSError('Gravação incompleta do save.')
            stream.flush()
            os.fsync(stream.fileno())
            stream.seek(0)
            if fingerprint(stream.read()) != fingerprint(payload):
                raise OSError('A verificação da gravação falhou.')
        except Exception:
            stream.seek(0)
            stream.write(before)
            stream.flush()
            os.fsync(stream.fileno())
            raise
    return str(backup)


def prepare_request(game,request):
    """Reuse the completed inspection for offers; never reopen all three DBs."""
    if request['action']!='job_offer':
        return run_worker(game,request)
    original=Path(request['path']).read_bytes()
    if fingerprint(original)!=request['fingerprint']:
        raise ValueError('O save mudou. Reabra o painel e confirme o pedido novamente.')
    output=Path(request['output'])
    seed=request.get('job_offer_seed')
    # Recover an interrupted preparation only when it equals the exact patch
    # for this request and preserves every other original byte and checksum.
    if seed is None and output.is_file():
        candidate=output.read_bytes()
        try:
            offer=read_job_offer(candidate)
            candidate_seed={key:offer[key] for key in ('date','wage')}
            expected=stage_job_offer(original,request,candidate_seed)
            if candidate==expected:seed=candidate_seed
        except (ValueError,KeyError,TypeError):pass
    if seed is None:
        return run_worker(game,request)
    payload=stage_job_offer(original,request,seed)
    output.write_bytes(payload)
    if output.read_bytes()!=payload:
        raise OSError('A verificação do pedido preparado falhou.')
    return {'context':request['context'],'job_offer':read_job_offer(payload),
            'output_sha256':fingerprint(payload),'preparation':'verified_fixed_size_patch'}


class CareerService:
    def __init__(self, app):
        self.app = app
        self.context_reader = CareerContext(app)
        self.root = Path(app.base_dir)/'runtime/career_overlay'
        self.root.mkdir(parents=True, exist_ok=True)
        self.events = queue.Queue()
        self.busy = False
        self._inflight = set()
        self.revision = 0
        self.state = 'idle'
        self.message = ''
        self.saves = []
        self.catalog = None
        self.selected = None
        self.inspection = None
        self._disk_inspection = None
        self._disk_selected = None
        self._view_profile = None
        self.pending = None
        self._prepared_result = None
        self.generation = 0
        self._safe_since = None
        self._notice_until = 0
        self._job_token = None
        self._next_active_check = 0
        self.feedback = CareerFeedback(app)
        self.jobs_runtime = CareerJobsRuntime(app)
        self._next_preload = 0
        self._live_history = []
        self._live_started = 0
        self._load_live_history()
        self._restored_notice = False
        self._load_pending()

    def _load_pending(self):
        path = self.root/'pending.json'
        if path.is_file():
            try:
                request = json.loads(path.read_text(encoding='utf-8'))
                if request.get('action') in ('funds', 'job_offer', 'transfer', 'remove_retirement', 'remove_and_rejuvenate') and Path(request['path']).is_file():
                    if request['action']=='transfer' and request.get('context',{}).get('player_id') is None:
                        request['action']='job_offer'
                    self.pending = request
                    self.state = 'waiting_exit'
                    self.message = 'Pedido confirmado. Saia da carreira para aplicar.'
                    self._restored_notice = True
            except (OSError, ValueError, KeyError, TypeError):
                self.message = 'Pedido anterior inválido. Faça um novo pedido.'

    def _job(self, kind, callback, token=None):
        if self.busy and not (kind=='inspect' and self._inflight=={'catalog'}):
            return False
        self._inflight.add(kind)
        self.busy = True
        self._job_token = token
        def work():
            started = time.perf_counter()
            try:
                self.events.put((kind, token, callback(), None))
            except Exception as exc:
                self.events.put((kind, token, None, str(exc)))
            finally:
                self.app.log(f'Career {kind}: {time.perf_counter()-started:.3f}s')
        threading.Thread(target=work, name='career-'+kind, daemon=True).start()
        return True

    def notify(self, stage, message, request=None):
        request=request or self.pending or {}
        token=request.get('request_id') or request.get('fingerprint') or 'career'
        persistent=(request.get('action') in ('funds','remove_retirement','remove_and_rejuvenate')
                    and stage in ('prepared','waiting_exit','applying'))
        try:self.feedback.show(stage,message,token,persistent=persistent)
        except Exception as exc:self.app.log('Career feedback unavailable',exc)

    def load(self):
        if self.pending or self.busy:
            return
        self.state, self.message = 'loading', 'Lendo os clubes instalados…'
        game = Path(getattr(self.app, 'exedir', self.app.base_dir))
        self._job('catalog', lambda: self._read(game, {'op':'catalog'}))

    def _read(self, game, request):
        try:
            return read_career(game, request)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            self.app.log('Career fast reader unavailable; using editing bridge', exc)
            return run_worker(game, request)

    def select(self, selected):
        if self.pending or (self.busy and self._inflight!={'catalog'}):
            return
        self.selected = selected
        self.inspection = None
        self.generation += 1
        self.state, self.message = 'loading', 'Lendo a carreira em execução…'
        game = Path(getattr(self.app, 'exedir', self.app.base_dir))
        self._job('inspect', lambda: self._read(game, {'op':'inspect', 'path':selected['path']}), self.generation)

    def active_save(self):
        game = Path(getattr(self.app, 'exedir', self.app.base_dir))
        return read_active_save(game, self.app.memory)

    def _forget_active(self, message):
        if self.selected or self.inspection or self.message != message:
            self.selected = self.inspection = None
            self._disk_inspection = self._disk_selected = self._view_profile = None
            self.generation += 1
            self.state, self.message = 'detecting', message
            self.revision += 1

    @staticmethod
    def _profile_key(profile):
        if not profile:return None
        return tuple(profile.get(key) for key in ('userid','club_id','career_role','registry_address','context_address'))

    def _bind_inspection(self, result, profile):
        """Keep disk data cached; a signed contract changes RAM before the next save."""
        key = self._profile_key(profile)
        if self._view_profile != key:
            self.generation += 1
        self._view_profile = key
        context = result['context']
        if not profile or profile.get('userid') != context['userid']:
            self.inspection = None
            self.state,self.message = 'waiting_save','Salve a carreira atual no FIFA para atualizar os dados.'
        elif profile['club_id'] == context['club_id']:
            self.inspection = result
            self.state,self.message = 'ready','Carreira em execução identificada automaticamente.'
        elif context['player_id'] is None and profile.get('career_role',1) == 1:
            team = next((row for row in result['catalog']['teams'] if row['id']==profile['club_id']),None)
            if team is None:
                self.inspection = None
                self.state,self.message = 'waiting_save','Salve a carreira após mudar de clube para atualizar os dados.'
            else:
                # Club identity comes from the verified live career service.
                # The old club's budget must never be presented as the new one's.
                live = dict(context,club_id=profile['club_id'],club=team['name'],budget=None,currency=None)
                self.inspection = dict(result,context=live,save_synced=False)
                self.state,self.message = 'ready','Clube atualizado. Salve a carreira no FIFA para atualizar as finanças.'
        else:
            self.inspection = None
            self.state,self.message = 'waiting_save','A carreira mudou. Salve o progresso no FIFA para atualizar os dados.'
        self.revision += 1

    def sync_active(self):
        if self.pending or (self.busy and self._inflight!={'catalog'}):
            return
        now = time.monotonic()
        if now < self._next_active_check:
            return
        self._next_active_check = now + 1
        if not self.in_career(self.live_page()):
            if self.state == 'done':
                return
            self._forget_active('Abra uma carreira para usar estas opções.')
            return
        try:
            selected = self.active_save()
            profile = self.context_reader.profile(fresh=True)
            if (self._disk_inspection is not None and self._disk_selected
                    and version(selected) == version(self._disk_selected)):
                # Poll only the live identity, not the unchanged file.
                if self._profile_key(profile) != self._view_profile:
                    self._bind_inspection(self._disk_inspection,profile)
                return
            if self.selected and version(selected) == version(self.selected) and self.inspection:
                if profile and all(profile.get(k)==self.inspection['context'][k] for k in ('userid','club_id')):
                    return
                self._disk_inspection,self._disk_selected = self.inspection,dict(selected)
                self._bind_inspection(self._disk_inspection,profile)
                return
            self.select(selected)
        except (OSError, RuntimeError, ValueError) as exc:
            self._forget_active(str(exc))

    def require_active(self, allow_live=False):
        if self.busy or not self.inspection or not self.selected:
            raise ValueError(self.message or 'Aguardando a identificação automática da carreira.')
        selected = self.active_save()
        profile = self.context_reader.profile(fresh=True)
        if version(selected) != version(self.selected):
            self._next_active_check = 0
            self.inspection = None
            raise ValueError('O progresso mudou. Aguarde a atualização automática da carreira.')
        context = self.inspection['context']
        if not profile or any(profile.get(key) != context[key] for key in ('userid', 'club_id')):
            self._disk_inspection = self._disk_inspection or self.inspection
            self._disk_selected = self._disk_selected or dict(self.selected)
            self._bind_inspection(self._disk_inspection,profile)
            raise ValueError('A carreira mudou. Revise os dados atualizados antes de confirmar.')
        if not allow_live and self.inspection.get('save_synced') is False:
            raise ValueError('Você mudou de clube. Salve a carreira no FIFA antes de solicitar verba ou aposentadoria.')
        return selected

    def confirm(self, action, **values):
        if self.pending:
            raise ValueError('Já existe um pedido aguardando aplicação.')
        if not self.in_career(self.live_page()) or not self.app.memory.is_open():
            raise ValueError('Abra o pedido dentro da carreira.')
        self.require_active(allow_live=action=='transfer' and
                            (self.inspection or {}).get('context',{}).get('player_id') is None)
        request = {'request_id':uuid.uuid4().hex,'action': action, 'path': self.selected['path'],
                   'title':self.selected['title'], 'context':self.inspection['context'],
                   'fingerprint':self.inspection['fingerprint'], **values}
        if action == 'funds':
            amount = values.get('amount')
            if type(amount) is not int or not 0 < amount <= MAX_MONEY:
                raise ValueError('Informe uma verba entre 1 e 2 bilhões.')
            if request['context']['player_id'] is not None:
                raise ValueError('Verba disponível na carreira de treinador.')
            if request['context']['budget'] + amount > MAX_MONEY:
                raise ValueError('O orçamento total ultrapassaria 2 bilhões.')
        elif action in ('remove_retirement', 'remove_and_rejuvenate'):
            game = Path(getattr(self.app, 'exedir', self.app.base_dir))
            request['target_age'] = retirement_age(game)
        elif action == 'transfer':
            data=transfer_catalog(self.inspection['catalog'],self.catalog)
            if not any(league==values['league_id'] and team==values['team_id'] for league,team in data['links']):
                raise ValueError('Escolha um clube de uma divisão disponível. Seleções, agentes livres e divisões de acesso não são destinos.')
            if request['context']['player_id'] is None:
                profile=self.context_reader.profile(fresh=True) or {}
                request['team_name']=next((r['name'] for r in data['teams'] if r['id']==values['team_id']),str(values['team_id']))
                self._start_live_request(request,profile)
                return
            from .competition_catalog import nodes
            league = values['league_id']
            matches = [ident for ident, row in nodes(getattr(self.app,'exedir',self.app.base_dir)).items()
                       if row[0] == 3 and row[1] == 'C'+str(league)]
            if len(matches) != 1 or not 0 < matches[0] <= 2000:
                raise ValueError('Competição principal do destino não identificada na instalação.')
            request['primarycompobjid'] = matches[0]
            if values['team_id'] == request['context']['club_id']:
                raise ValueError('Você já está nesse clube.')
        else:
            raise ValueError('Pedido desconhecido.')
        temporary = self.root/'pending.tmp'
        temporary.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.root/'pending.json')
        self.pending = request
        self._prepared_result = None
        self.state, self.message = 'waiting_exit', 'Pedido aceito. Saia da carreira sem salvar novamente.'
        self._safe_since = None
        self.revision += 1
        title=('Pedido de aposentadoria preparado.' if action in ('remove_retirement', 'remove_and_rejuvenate') else
               'Pedido de proposta preparado.' if request['action']=='job_offer' else
               'Transferência preparada.' if action=='transfer' else 'Solicitação de verba preparada.')
        self.notify('prepared',title+'\nSaia do save sem salvar.\nAguarde a confirmação antes de reabrir.')

    def cancel(self):
        if self.busy:
            return
        (self.root/'pending.json').unlink(missing_ok=True)
        cancelled=self.pending
        self.pending = None
        self._prepared_result = None
        self.state, self.message = 'idle', 'Pedido cancelado. O save não foi alterado.'
        self.revision += 1
        self.notify('cancelled','Pedido cancelado.\nO save não foi alterado.',cancelled)

    def _load_live_history(self):
        try:
            rows=json.loads((self.root/'live_jobs.json').read_text(encoding='utf8'))
            if isinstance(rows,list):self._live_history=rows[-128:]
        except (OSError,ValueError):pass
        try:
            legacy=json.loads((self.root/'last_applied.json').read_text(encoding='utf8'))
            if legacy.get('action')=='job_offer':self._live_history.append(legacy)
        except (OSError,ValueError):pass

    def _start_live_request(self,request,profile,recovery=False):
        if request['team_id']==request['context']['club_id']:
            raise ValueError('Você já está nesse clube.')
        ticket=self.jobs_runtime.request(profile,request['team_id'],request['league_id'])
        self.pending=dict(request,action='live_job',ticket=ticket,runtime_pid=self.jobs_runtime.pid,
                          runtime_epoch=self.jobs_runtime.shared.load_epoch)
        self._live_started=time.monotonic()
        self.state,self.message='waiting_runtime','Feche o painel e aguarde na Central, sem avançar a data.'
        self.revision+=1
        if not recovery:
            self.notify('prepared','Pedido enviado. Volte à Central e aguarde o contrato.\nNão é preciso avançar a data.')

    def _poll_live_request(self):
        request=self.pending
        if not request or request.get('action')!='live_job':return False
        try:
            if (self.jobs_runtime.pid!=request['runtime_pid']
                    or self.jobs_runtime.shared is None
                    or self.jobs_runtime.shared.load_epoch!=request['runtime_epoch']):
                raise ValueError('O jogo ou a carreira mudou durante o pedido. Abra o painel e revise o clube novamente.')
            result=self.jobs_runtime.poll(request['ticket'],request['team_id'],request['league_id'])
            if result is None:
                if time.monotonic()-self._live_started>5:
                    self.message='Aguarde na Central, em tempo real. Não avance dias para receber a proposta.'
                if time.monotonic()-self._live_started>90:
                    raise ValueError('A proposta não ficou pronta em 90 segundos. Não avance datas para tentar recebê-la. Reinicie o FIFA e o Server.')
                return True
            if result.get('proposal_received') is not True or result.get('native_contract_queued') is not True:
                raise ValueError('O FIFA ainda não confirmou a proposta e a entrada do contrato.')
            receipt=dict(request,result=result)
            self.pending=None
            self.state,self.message='ready','Oferta criada. Abertura do contrato solicitada ao FIFA.'
            self._notice_until=0
            self.revision+=1
            self.app.log('Career native proposal confirmed: '+str(request['team_id']))
            days=result.get('valid_for_days',0)
            expiry=(f'Prazo: {days} dias de jogo.' if isinstance(days,int) and days>0
                    else 'Confira o prazo na proposta antes de avançar a data.')
            self.notify('done','Proposta de '+request.get('team_name',str(request['team_id']))+' confirmada.\nAceite ou recuse no contrato do FIFA.\n'+expiry,receipt)
            key=lambda row:(str(row.get('path','')).casefold(),row.get('context',{}).get('club_id'),row.get('team_id'),row.get('league_id'))
            self._live_history=[r for r in self._live_history if key(r)!=key(receipt)]+[receipt]
            try:
                (self.root/'live_jobs.json').write_text(json.dumps(self._live_history[-128:],ensure_ascii=False,indent=2),encoding='utf8')
                (self.root/'last_live_applied.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
            except OSError as exc:self.app.log('Career live vacancy confirmed; journal failed',exc)
        except (OSError,RuntimeError,ValueError) as exc:
            self.pending=None
            self.state,self.message='error',str(exc)
            self.revision+=1
            self.notify('error','O FIFA não confirmou a proposta.\n'+str(exc),request)
        return True

    def preload(self):
        now=time.monotonic()
        if now<self._next_preload:return
        self._next_preload=now+2
        if not self.app.memory.is_open():return
        if not self.pending and self.catalog is None and not self.busy and self.state!='error':self.load()
        if self.in_career(self.live_page()):self.jobs_runtime.ensure()

    def restore_live_vacancies(self):
        # History is a receipt, not an instruction. Native save serialization
        # preserves received offers; never resurrect refused/expired offers.
        return

    def live_page(self):
        reader = getattr(self.app.memory, 'get_string', None)
        offsets = getattr(self.app, 'offsets', None)
        if callable(reader) and offsets is not None:
            try:
                return reader(offsets.ORIPGBASE, offsets.PG1, size=64)
            except Exception:
                return ''
        return self.app.lastpagename

    def safe_to_apply(self, fresh=False):
        if not self.app.memory.is_open():
            # A failed RAM attachment is not evidence that FIFA has exited.
            resolver = getattr(self.app, '_resolve_fifa_pid', None)
            return not resolver() if callable(resolver) else False
        running = getattr(self.app, '_is_game_running_with', lambda memory: False)(self.app.memory)
        page = self.live_page()
        return (safe_exit_page(page) or self.context_reader.exited_hub(page,fresh=fresh)) and not running

    def in_career(self, page):
        self.context_reader.observe(page)
        return career_page(page) or self.context_reader.career_hub(page)

    def tick(self):
        self.feedback.tick()
        self.preload()
        live_pending=self._poll_live_request()
        if self._restored_notice:
            self._restored_notice=False
            self.notify('prepared','Pedido preparado.\nSaia do save sem salvar e aguarde a aplicação.')
        while True:
            try:
                kind, token, result, error = self.events.get_nowait()
            except queue.Empty:
                break
            self._inflight.discard(kind)
            self.busy = bool(self._inflight)
            self.revision += 1
            if error:
                self.state, self.message = 'error', error
                self.app.log('Career overlay job failed: '+error)
                if kind=='prepare':self.notify('error','Pedido não aplicado.\n'+error)
                continue
            if kind == 'catalog':
                self.catalog = result
                self.state, self.message = ('ready','Carreira em execução identificada automaticamente.') if self.inspection else ('detecting','Identificando a carreira em execução…')
                self._next_active_check = 0
            elif kind == 'inspect' and token == self.generation:
                try:
                    active = self.active_save()
                    profile = self.context_reader.profile(fresh=True)
                    if (not self.in_career(self.live_page())
                            or version(active) != version(self.selected)):
                        raise ActiveCareerUnavailable('A carreira mudou durante a leitura. Atualizando…')
                except (OSError, RuntimeError, ValueError, TypeError) as exc:
                    self._forget_active(str(exc))
                    continue
                self._disk_inspection,self._disk_selected = result,dict(active)
                self._bind_inspection(result,profile)
            elif kind == 'prepare':
                self._prepared_result=result
                if not self.pending or not self.safe_to_apply(fresh=True):
                    self.state, self.message = 'waiting_exit', 'Aguarde no menu principal para aplicar.'
                    self._safe_since = None
                    self.notify('waiting_exit','Pedido ainda não aplicado.\nSaia da carreira sem salvar e aguarde no menu principal.')
                    continue
                try:
                    # Publication runs on the UI tick after rechecking the live
                    # RAM page. No background job can publish while playing.
                    output = self.root/'prepared_DATA'
                    payload=output.read_bytes()
                    if result.get('output_sha256') and fingerprint(payload)!=result['output_sha256']:
                        raise ValueError('O pedido preparado mudou. Cancele e confirme novamente.')
                    backup = publish_save(self.pending['path'], self.pending['fingerprint'],
                                          payload, self.root/'backups')
                    receipt = dict(self.pending, result=result['context'], backup=backup)
                    if 'job_offer' in result:receipt['job_offer']=result['job_offer']
                    if 'retirement' in result:receipt['retirement']=result['retirement']
                    self.pending = None
                    self._prepared_result = None
                    self.inspection = None
                    self.state, self.message = 'done', 'Aplicado com backup. Carregue novamente a carreira.'
                    self._notice_until = time.monotonic()+30
                    self.app.log('Career save updated; backup: '+backup)
                    text=('Pedido aplicado. Reabra esta carreira.\nO clube enviará uma proposta pelo FIFA.'
                          if receipt['action']=='job_offer' else
                          'Alteração aplicada com sucesso.\nO save está pronto para ser reaberto.')
                    if 'retirement' in result:
                        summary = result['retirement']
                        text=(f"Aposentadoria removida de {summary['players_changed']} jogador(es).\n"+
                              (f"Idade redefinida para {summary['target_age']} anos.\n"
                               if receipt['action']=='remove_and_rejuvenate' else '')+
                              'Aplicado e validado. Reabra esta carreira.')
                    elif receipt['action']=='funds':
                        text=(f"Verba aplicada: +{receipt['amount']:,}.\n"+
                              f"Novo orçamento: {result['context']['budget']:,}.\nReabra esta carreira.").replace(',', '.')
                    self.notify('done',text,receipt)
                    # A log/journal failure after successful publication must
                    # never be reported as an unapplied request.
                    try:
                        (self.root/'last_applied.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
                        (self.root/'pending.json').unlink(missing_ok=True)
                    except OSError as exc:
                        self.app.log('Career save applied; journal cleanup failed', exc)
                except Exception as exc:
                    self.state, self.message = 'error', str(exc)
                    self.app.log('Career save publication failed', exc)
                    self.notify('error','Pedido não aplicado.\n'+str(exc))
        self.sync_active()
        self.restore_live_vacancies()
        if live_pending or (self.pending and self.pending.get('action')=='live_job'):return
        if not self.pending or self.busy or self.state == 'error':
            return
        if not self.safe_to_apply():
            self._safe_since = None
            return
        now = time.monotonic()
        if self._safe_since is None:
            self._safe_since = now
        if now-self._safe_since < 2:
            return
        if self._prepared_result is not None:
            self.events.put(('prepare',self.pending.get('request_id'),self._prepared_result,None))
            self._prepared_result=None
            self.busy=True
            return
        self.state, self.message = 'applying', 'Aplicando no save. Aguarde antes de carregar a carreira…'
        self.notify('applying','Aplicando a alteração no save.\nAguarde a confirmação antes de reabrir.')
        self.revision += 1
        request = dict(self.pending, op='prepare', output=str((self.root/'prepared_DATA').resolve()))
        game = Path(getattr(self.app, 'exedir', self.app.base_dir))
        self._job('prepare', lambda: prepare_request(game, request))

    def notice_available(self):
        return self.state == 'done' and time.monotonic() < self._notice_until
