"""Consume native options through the existing per-fixture crowd bridge."""
from pathlib import Path
import ctypes
import re
import time

REQUEST='ModCarrerMode/runtime/crowd_selector/request.tsv'


def read_request(path,pid,created,context,now_ms):
    path=Path(path)
    if path.stat().st_size>512:raise ValueError('Attendance request too large')
    raw=path.read_bytes()
    if len(raw)>512:raise ValueError('Attendance request too large')
    fields=dict(line.split('=',1) for line in raw.decode('ascii').splitlines() if '=' in line)
    if (fields.get('schema')!='1' or int(fields.get('pid','0'))!=pid
            or abs(int(fields.get('created','0'))-created)>10000):
        raise ValueError('Attendance request belongs to another process')
    fixture=tuple(int(fields.get(key,'-1')) for key in ('generation','home','away'))
    age=now_ms-int(fields.get('captured_tick','0'))
    if fixture!=tuple(context) or not 0<=age<=10000:
        raise ValueError('Attendance request belongs to another fixture')
    match=re.fullmatch(r'S16CROWD1\|(-1|0|[1-9]\d?|100)\|END',fields.get('wire',''))
    if not match:raise ValueError('Invalid attendance percentage')
    value=int(match[1])
    if value!=-1 and value%5:raise ValueError('Invalid attendance step')
    return value


class NativeAttendance:
    def __init__(self,control):
        self.control=control;self.stamp=None;self.pending=None;self.next_poll=0.

    def tick(self):
        now=time.monotonic()
        if now<self.next_poll:return
        self.next_poll=now+.2
        control=self.control;app=control.app;shared=control.shared
        if shared.phase not in (1,2):
            self.pending=None
            return
        path=Path(getattr(app,'exedir',app.base_dir))/REQUEST
        try:
            stat=path.stat();stamp=(stat.st_mtime_ns,stat.st_size,shared.game_pid)
            if stamp!=self.stamp:
                self.stamp=stamp
                import psutil
                created=round((psutil.Process(shared.game_pid).create_time()+11644473600)*10_000_000)
                tick=ctypes.windll.kernel32.GetTickCount64
                tick.restype=ctypes.c_ulonglong
                value=read_request(path,shared.game_pid,created,control.context,tick())
                self.pending=(control.context,value,now+5)
        except FileNotFoundError:pass
        except (OSError,ValueError,UnicodeError) as error:
            self.pending=None;app.log('Native attendance request rejected',error)
        except Exception as error:
            self.pending=None;app.log('Native attendance session unavailable',error)
        if self.pending is None:return
        fixture,value,deadline=self.pending
        if fixture!=control.context or now>deadline:
            self.pending=None;return
        if value==-1:
            control.clear();self.pending=None
            app.log('Native attendance: automatic crowd rule restored')
        elif shared.status in (2,3) and shared.ack==shared.command:
            control.apply(value,fixture,native_request=True);self.pending=None
            app.log(f'Native attendance requested: {value}% for fixture {fixture}')
