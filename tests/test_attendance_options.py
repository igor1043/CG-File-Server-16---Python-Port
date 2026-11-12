import tempfile,unittest
import os,ctypes,psutil
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
from server16_py.attendance_options import read_request,NativeAttendance,REQUEST


class AttendanceRequests(unittest.TestCase):
    def test_native_choice_waits_for_bridge_and_never_survives_another_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pid=os.getpid();context=(9,1043,567)
            shared=SimpleNamespace(phase=1,game_pid=pid,status=1,ack=1,command=1)
            app=SimpleNamespace(exedir=root,base_dir=root,log=Mock())
            control=SimpleNamespace(shared=shared,app=app,context=context,apply=Mock(),clear=Mock())
            native=NativeAttendance(control);p=root/REQUEST;p.parent.mkdir(parents=True)
            created=round((psutil.Process(pid).create_time()+11644473600)*10_000_000)
            tick=ctypes.windll.kernel32.GetTickCount64;tick.restype=ctypes.c_ulonglong
            p.write_text(f'schema=1\npid={pid}\ncreated={created}\ngeneration=9\nhome=1043\naway=567\ncaptured_tick={tick()}\nwire=S16CROWD1|65|END\n')
            native.tick();control.apply.assert_not_called()
            shared.status=2;native.next_poll=0;native.tick()
            control.apply.assert_called_once_with(65,context,native_request=True)
            native.next_poll=0;native.tick();self.assertEqual(control.apply.call_count,1)
            native.pending=(context,65,float('inf'));control.context=(10,567,1043)
            native.next_poll=0;native.tick();self.assertIsNone(native.pending)

    def test_all_percentages_and_automatic_are_bound_to_the_exact_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'request.tsv'
            def write(value,**changes):
                fields=dict(schema=1,pid=42,created=123456,generation=9,home=1043,away=567,captured_tick=1000,wire=f'S16CROWD1|{value}|END')
                fields.update(changes);p.write_text('\n'.join(f'{k}={v}' for k,v in fields.items()),encoding='ascii')
            for v in (-1,*range(0,101,5)):
                write(v);self.assertEqual(read_request(p,42,123456,(9,1043,567),1005),v)
            for v in (-5,101,65.0,3,'065','65|END|OTHER','NaN'):
                write(v)
                with self.assertRaises(ValueError):read_request(p,42,123456,(9,1043,567),1005)
            for changes in (dict(pid=43),dict(created=999999),dict(generation=10),dict(home=567),dict(away=1043),dict(captured_tick=-9001),dict(captured_tick=1006)):
                write(65,**changes)
                with self.assertRaises(ValueError):read_request(p,42,123456,(9,1043,567),1005)


if __name__=='__main__':unittest.main()
