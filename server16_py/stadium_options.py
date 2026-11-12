"""Fixture-bound bridge from native GameSettings to the installed stadium picker."""
from pathlib import Path
import hashlib,json,os,time

PAGE='game/screens/settings/GameSettings'
RUNTIME='ModCarrerMode/runtime/stadium_options'

def context(app):
    return (app._kickoff_generation,app.HID,app.AID,app.TOURNAME,app.TOURROUNDID)

def owns_settings(app):
    return ((getattr(app,'lastpagename','') or '').casefold()==PAGE.casefold()
        and getattr(app,'_native_stadium_options_context',None)==context(app)
        and app.memory.is_open() and not getattr(app,'_stadium_fixture_entered',False))

def read_event(app,path,pid):
    import psutil
    if path.stat().st_size>1024:raise ValueError('Solicitação de opções excedeu o limite')
    raw=path.read_bytes();data=dict(row.split('=',1) for row in raw.decode('ascii').splitlines() if '=' in row)
    created=round((psutil.Process(pid).create_time()+11644473600)*10_000_000)
    if data.get('schema')!='1' or int(data.get('pid','0'))!=pid or abs(int(data.get('created','0'))-created)>10000:raise ValueError('Solicitação de outra sessão')
    import ctypes
    clock=ctypes.windll.kernel32.GetTickCount64;clock.restype=ctypes.c_uint64
    age=clock()-int(data.get('captured_tick','0'))
    if not 0<=age<=15000:raise ValueError('Solicitação expirada')
    return data

def publish_refresh(app,entry):
    if app.memory.process_id!=int(entry['pid']):return
    root=Path(app.exedir)/RUNTIME;root.mkdir(parents=True,exist_ok=True)
    text='schema=1\npid='+entry['pid']+'\ncreated='+entry['created']+'\nentry_tick='+entry['captured_tick']+'\n'
    revision=hashlib.sha256((text+str(time.time_ns())).encode()).hexdigest();text+='revision='+revision+'\n'
    path=root/'refresh.tsv';temp=path.with_suffix('.tsv.new');temp.write_text(text,encoding='ascii');os.replace(temp,path)

def poll_native_options(service,page,pid):
    app=service.app;root=service.root/RUNTIME
    if page!=PAGE:return
    for filename,attribute in (('enter.tsv','enter_stamp'),('open.tsv','open_stamp')):
        try:
            path=root/filename;info=path.stat();stamp=(pid,info.st_mtime_ns,info.st_size)
            if stamp==getattr(service,attribute):continue
            setattr(service,attribute,stamp);event=read_event(app,path,pid)
            if filename=='enter.tsv':
                service.native_entry=event
                current=context(app)
                if current!=service.stadium_context:
                    service.stadium=None;service.stadium_context=current
                service._submit(service._prepare,service.root,event)
            else:
                selector=getattr(app,'_stadium_selector',None)
                if selector is None or not app.module_enabled('Stadium') or getattr(app,'_stadium_fixture_entered',False):raise ValueError('Seletor de estádio indisponível')
                crowd=selector.crowd_control.shared
                expected=tuple(int(event.get(key,'-1')) for key in ('generation','home','away'))
                if (crowd.game_pid!=pid or crowd.phase!=1 or expected!=(crowd.generation,crowd.home_id,crowd.away_id)
                    or (str(crowd.home_id),str(crowd.away_id))!=(str(app.HID),str(app.AID))):raise ValueError('A partida mudou')
                if selector.shared.ready!=7:raise ValueError('Aguarde a preparação do seletor de estádios')
                app._native_stadium_options_context=context(app);selector.open(settings=True)
        except FileNotFoundError:pass
        except Exception as error:app.log('Native match options request rejected',error)

def applied_stadium(service,name,slot):
    app=service.app;candidate=getattr(service,'stadium_candidate',None)
    if not owns_settings(app) or not candidate or candidate.name!=name:return
    service.stadium_context=context(app)
    service.stadium={'id':int(slot),'title':getattr(app,'ScoreboardStadName','') or candidate.title or candidate.name,
                     'preview':str(candidate.preview) if candidate.preview and candidate.preview.is_file() else None}
    service._submit(service._prepare,service.root,getattr(service,'native_entry',None))
