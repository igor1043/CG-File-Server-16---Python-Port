"""Explicit retirement requests to the native career owner, never a save editor.

Requests expire and are not recovered/replayed on startup. Success describes the
loaded session; normal FIFA saving is what persists it to DATA/INDEX.
"""
from pathlib import Path
import ctypes
import secrets
import time


def fields(path):
    path=Path(path)
    if path.stat().st_size>8192:raise ValueError('Resposta de aposentadoria inválida.')
    rows=path.read_text(encoding='ascii').splitlines()
    result={}
    for row in rows:
        key,value=row.split('=',1)
        if key in result:raise ValueError('Resposta de aposentadoria duplicada.')
        result[key]=value
    return result


def process_created(memory):
    values=[ctypes.c_uint64() for _ in range(4)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetProcessTimes.argtypes=[ctypes.c_void_p]+[ctypes.POINTER(ctypes.c_uint64)]*4
    kernel.GetProcessTimes.restype=ctypes.c_int
    if not kernel.GetProcessTimes(memory.process_handle,*(ctypes.byref(v) for v in values)):
        raise ValueError('Não foi possível validar a sessão do FIFA.')
    return values[0].value


def ticks():
    kernel=ctypes.WinDLL('kernel32');kernel.GetTickCount64.restype=ctypes.c_uint64
    return kernel.GetTickCount64()


class RetirementRuntime:
    def __init__(self,app):
        self.app=app
        game=Path(getattr(app,'exedir',app.base_dir))
        self.root=game/'ModCarrerMode/runtime/career_options'

    def request(self,profile,rejuvenate,age):
        if not profile or profile.get('career_role')!=1:
            raise ValueError('Aposentadoria disponível somente na carreira de treinador.')
        if type(age) is not int or not 12<=age<=50:
            raise ValueError('Idade-alvo fora do intervalo de 12 a 50 anos.')
        try:ready=fields(self.root/'retirement_ready.tsv')
        except (OSError,UnicodeError,ValueError):
            raise ValueError('Abra a tela Aposentadoria e aguarde a integração. Se necessário, atualize a DLL e reinicie o FIFA.') from None
        now=ticks();memory=self.app.memory
        ticket=dict(pid=int(memory.process_id),created=process_created(memory),
                    epoch=profile.get('context_epoch'),context=profile.get('context_address'),
                    registry=profile.get('registry_address'),club=profile.get('club_id'))
        expected=dict(schema='1',pid=str(ticket['pid']),created=str(ticket['created']),
                      epoch=str(ticket['epoch']),context=f"{ticket['context']:x}",
                      registry=f"{ticket['registry']:x}",club=str(ticket['club']))
        if any(ready.get(k)!=v for k,v in expected.items()) or not 0<=now-int(ready.get('tick',0))<=5000:
            raise ValueError('A carreira mudou ou a integração expirou. Reabra Aposentadoria e aguarde.')
        today=int(ready['date'])
        if not 19000101<=today<=24001231:raise ValueError('Data da carreira inválida.')
        ticket.update(id=secrets.token_hex(16),date=today,started=time.monotonic())
        raw=(f"1 {ticket['pid']} {ticket['created']} {ticket['epoch']} {ticket['context']:x} "
             f"{ticket['registry']:x} {ticket['club']} {today} {ticket['id']} {int(bool(rejuvenate))} {age} {now}\n")
        temporary=self.root/'retirement_request.new'
        temporary.write_text(raw,encoding='ascii');temporary.replace(self.root/'retirement_request.tsv')
        return ticket

    def poll(self,ticket,profile):
        memory=self.app.memory
        if (not profile or profile.get('career_role')!=1 or int(memory.process_id)!=ticket['pid']
            or any(profile.get(key)!=ticket[name] for key,name in
                   (('context_epoch','epoch'),('context_address','context'),('registry_address','registry'),('club_id','club')))):
            raise ValueError('A carreira mudou durante o pedido. Nenhum pedido será repetido no novo save.')
        try:response=fields(self.root/'retirement_response.tsv')
        except (FileNotFoundError,PermissionError):response={}
        expected=dict(schema='1',id=ticket['id'],pid=str(ticket['pid']),created=str(ticket['created']),
                      epoch=str(ticket['epoch']),context=f"{ticket['context']:x}",club=str(ticket['club']))
        if all(response.get(k)==v for k,v in expected.items()):
            status=int(response['status'])
            if status==3:
                raise ValueError('Não foi possível restaurar todos os dados do pedido. Saia da carreira sem salvar e reabra o último save.')
            if status!=0:
                raise ValueError('Pedido recusado ou alterações restauradas. Reabra Aposentadoria para conferir a carreira.')
            changed=int(response['changed']);eligible=int(response['eligible'])
            if not 0<=changed==eligible<=50000:raise ValueError('Contagem da confirmação nativa inválida.')
            return dict(players_changed=changed,players_retiring=eligible,native_save_pending=True)
        if time.monotonic()-ticket['started']>20:
            raise ValueError('O FIFA não confirmou o pedido. Ele não será repetido automaticamente. Reabra a tela para conferir antes de salvar.')
        return None
