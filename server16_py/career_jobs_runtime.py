"""Actionable career proposals through FIFA's provider owner thread."""
from __future__ import annotations
import ctypes
import mmap
import os
import sys
import threading
from pathlib import Path
from .shutdown import run_owned_reader

MAGIC=0x164a4f42
VERSION=4
CAPACITY=16


def _loaded_runtime_paths(pid):
    from .memory_access import Memory,MODULEENTRY32W,INVALID_HANDLE_VALUE
    probe=Memory();kernel=probe.kernel32
    snapshot=kernel.CreateToolhelp32Snapshot(24,pid)
    if not snapshot or snapshot==INVALID_HANDLE_VALUE:
        raise OSError('Não foi possível verificar os módulos de propostas do FIFA.')
    try:
        entry=MODULEENTRY32W();entry.dwSize=ctypes.sizeof(entry)
        ok=kernel.Module32FirstW(snapshot,ctypes.byref(entry));matches=[]
        if not ok:raise OSError('Não foi possível ler os módulos do FIFA.')
        while ok:
            if entry.szModule.casefold().startswith('career_jobs_runtime.dll'):
                matches.append(Path(entry.szExePath))
            ok=kernel.Module32NextW(snapshot,ctypes.byref(entry))
        return matches
    finally:kernel.CloseHandle(snapshot)


class JobsShared(ctypes.Structure):
    _fields_=[('magic',ctypes.c_uint32),('version',ctypes.c_uint32),('pid',ctypes.c_uint32),
        ('ready',ctypes.c_uint32),('heartbeat',ctypes.c_uint32),('sequence',ctypes.c_int32),
        ('completed',ctypes.c_int32),('status',ctypes.c_int32),('source_club',ctypes.c_int32),
        ('team',ctypes.c_int32),('league',ctypes.c_int32),('count',ctypes.c_int32),
        ('registry',ctypes.c_uint64),('context',ctypes.c_uint64),('error',ctypes.c_uint32),
        ('load_epoch',ctypes.c_uint32),('request_epoch',ctypes.c_uint32),('reserved',ctypes.c_uint32),
        ('clubs',(ctypes.c_int32*2)*CAPACITY)]


class CareerJobsRuntime:
    def __init__(self,app):
        self.app=app
        self.pid=0
        self.mapping=None
        self.shared=None
        self.injecting=False
        self.attempted=0
        self.error=''

    def connect(self,pid):
        if pid==self.pid and self.shared is not None:return
        self.close()
        self.pid=pid
        self.mapping=mmap.mmap(-1,ctypes.sizeof(JobsShared),tagname=f'Local\\FIFA16CareerJobs_v{VERSION}_{pid}',access=mmap.ACCESS_WRITE)
        self.shared=JobsShared.from_buffer(self.mapping)

    def disabled(self):
        base=getattr(self.app,'exedir',getattr(self.app,'base_dir',None))
        return base is not None and (Path(base)/'ModCarrerMode/config/career_live_jobs.disabled').exists()

    def ready(self):
        s=self.shared
        if s is None or self.disabled():return False
        if s.magic==MAGIC and s.version==VERSION and s.pid==self.pid and s.error in (6,10):
            self.error='A integração de propostas foi interrompida. Reinicie o FIFA e o Server antes de tentar novamente.'
            return False
        now=ctypes.windll.kernel32.GetTickCount()&0xffffffff
        return (s.magic==MAGIC and s.version==VERSION and s.pid==self.pid and s.ready==1
                and ((now-s.heartbeat)&0xffffffff)<10000)

    def ensure(self):
        if self.disabled():
            self.error='Propostas suspensas após a falha. Reinicie o FIFA e o Server após a atualização.'
            return
        pid=int(getattr(self.app.memory,'process_id',0))
        if not pid:return
        self.connect(pid)
        if self.ready() or self.injecting or self.attempted==pid:return
        self.injecting=True;self.attempted=pid
        def inject():
            try:
                # Check modules even when the channel is absent/unready: an
                # older DLL or a failed initialization still owns game hooks.
                if _loaded_runtime_paths(pid):
                    raise RuntimeError('A integração anterior ainda está carregada. Reinicie o FIFA e o Server.')
                raise RuntimeError('Plugin de propostas não carregado. Instale o mod e reinicie o FIFA.')
            except Exception as exc:
                self.error=str(exc);self.app.log('Career live vacancies unavailable',exc)
            finally:self.injecting=False
        threading.Thread(target=inject,name='career-live-jobs-init',daemon=True).start()

    def request(self,profile,team,league):
        if not self.ready():raise ValueError(self.error or 'Preparando as propostas em memória. Aguarde alguns instantes.')
        if not profile.get('registry_address') or not profile.get('context_address'):
            raise ValueError('A carreira em execução não foi identificada. Aguarde a atualização.')
        s=self.shared
        if s.sequence!=s.completed or (s.sequence and not s.status):
            raise ValueError('Já há um pedido aguardando a confirmação do FIFA.')
        s.source_club=profile['club_id'];s.team=team;s.league=league
        s.registry=profile['registry_address'];s.context=profile['context_address']
        s.request_epoch=s.load_epoch;s.status=0;s.error=0
        s.reserved=ctypes.windll.kernel32.GetTickCount()&0xffffffff
        sequence=s.sequence+1
        s.sequence=sequence
        return sequence

    def poll(self,sequence,team,league):
        s=self.shared
        if s is None or s.magic!=MAGIC or s.version!=VERSION or s.pid!=self.pid:return None
        if s.completed!=sequence:return None
        if s.status==0:return None
        if s.status!=1:
            messages={1:'A carreira mudou. Abra o painel novamente e repita o pedido.',
                2:'O FIFA não confirmou os dados desse clube.',
                5:'A versão anterior ainda está em uso. Reinicie o FIFA e o Server para habilitar a substituição de propostas.',
                6:'A proposta não foi confirmada. Reinicie o FIFA e o Server antes de tentar novamente.'}
            messages[7]='A oferta mudou antes de abrir o contrato do FIFA. Volte à Central e faça o pedido novamente.'
            messages[8]='O pedido expirou sem abrir o contrato. Volte à Central e confirme um novo pedido.'
            messages[9]='O FIFA não confirmou a entrada da tela de contratação. O contrato não foi considerado aberto.'
            raise ValueError(messages.get(s.error,'O FIFA não confirmou a proposta.'))
        if not self.ready():return None
        rows=[tuple(s.clubs[i]) for i in range(min(max(s.count,0),CAPACITY))]
        if (team,league) not in rows:raise ValueError('O clube não foi confirmado na proposta.')
        return {'team_id':team,'league_id':league,'proposal_received':True,'native_contract_queued':True,
                'valid_for_days':int(s.reserved),
                'proposals':[list(row) for row in rows],
                'load_epoch':s.load_epoch,'save_edited':False}

    def close(self):
        self.shared=None
        if self.mapping is not None:self.mapping.close()
        self.mapping=None;self.pid=0
