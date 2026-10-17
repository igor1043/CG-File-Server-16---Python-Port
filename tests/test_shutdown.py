import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from server16_py.shutdown import cleanup_step,bounded_cleanup,finish_frozen_process


class ShutdownTests(unittest.TestCase):
    def app(self):
        path=Path(__file__).resolve().parents[1]/'server16_py/app.py'
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        methods=[node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name in ('on_close','_retry_close')]
        namespace=dict(sys=sys,cleanup_step=cleanup_step,bounded_cleanup=bounded_cleanup,restore_stadium_names=Mock(),finish_frozen_process=Mock(),close_owned_readers=Mock())
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods,type_ignores=[])),str(path),'exec'),namespace)
        cls=type('App',(),{name:namespace[name] for name in ('on_close','_retry_close')})
        app=cls();app._closing=False;app.log=Mock();app._stadium_selector=SimpleNamespace(shutdown=Mock(side_effect=RuntimeError('mapped view')))
        app.tk=SimpleNamespace(call=Mock(return_value=['timer1','timer2']));app.after_cancel=Mock();app.after=Mock()
        app._dismiss_launch_splash=Mock();app._show_closing_splash=Mock(return_value=None);app._hide_crowd_volume_popup=Mock()
        app._chants_stop=threading.Event();app._reset_team_entrance=Mock();app._reset_chants_state=Mock();app.discord_rpc=SimpleNamespace(disconnect=Mock())
        app._is_target_process_running=Mock(return_value=False);app._restore_native_runtime_assets=Mock()
        app._d3d_injector=SimpleNamespace(destroy=Mock());app.memory=SimpleNamespace(close=Mock());app.quit=Mock();app.destroy=Mock()
        return app

    def test_failure_does_not_skip_handles_or_windows_and_close_is_idempotent(self):
        app=self.app();app.on_close();self.assertTrue(app._shutdown_complete)
        app.memory.close.assert_called_once();app._d3d_injector.destroy.assert_called_once();app.destroy.assert_called_once()
        app.on_close();app.destroy.assert_called_once();self.assertTrue(app._chants_stop.is_set())

    def test_active_file_write_finishes_before_cleanup(self):
        app=self.app();app._bh_regen_running=True;app.on_close()
        self.assertFalse(app._closing);app.memory.close.assert_not_called();app.after.assert_called_once()
        app._bh_regen_running=False;app._retry_close();self.assertTrue(app._shutdown_complete)

    def test_network_cleanup_is_bounded(self):
        release=threading.Event();start=time.monotonic()
        bounded_cleanup('fixture',release.wait,Mock(),timeout=.02)
        self.assertLess(time.monotonic()-start,.5);release.set()

    def test_icon_import_finishes_before_cleanup(self):
        app=self.app();app.competition_icons=SimpleNamespace(busy=True);app.on_close()
        self.assertFalse(app._closing);app.memory.close.assert_not_called()
        app.competition_icons.busy=False;app._retry_close();self.assertTrue(app._shutdown_complete)

    def test_owned_database_reader_cannot_be_orphaned(self):
        import server16_py.shutdown as shutdown
        errors=[]
        def reader():
            try:shutdown.run_owned_reader([sys.executable,'-c','import time; time.sleep(60)'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except Exception as exc:errors.append(exc)
        with patch.object(shutdown,'_readers_closing',False):
            worker=threading.Thread(target=reader,daemon=True);worker.start()
            end=time.monotonic()+2;process=None
            while time.monotonic()<end:
                with shutdown._reader_lock:
                    if shutdown._readers:process=next(iter(shutdown._readers));break
                time.sleep(.005)
            self.assertIsNotNone(process)
            shutdown.close_owned_readers();worker.join(2)
            self.assertFalse(worker.is_alive());self.assertIsNotNone(process.poll())

    def test_source_entrypoint_never_forces_its_host_to_exit(self):
        with patch.object(sys,'frozen',False,create=True),patch('server16_py.shutdown.os._exit') as exit:
            finish_frozen_process();exit.assert_not_called()

    def test_frozen_exit_releases_file_despite_non_daemon_library_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'locked.dll';path.write_bytes(b'fixture')
            script='''import ctypes,sys,threading
from server16_py.shutdown import finish_frozen_process
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.CreateFileW.restype=ctypes.c_void_p
h=k.CreateFileW(sys.argv[1],0x80000000,1,None,3,0,None)
assert h not in (None,ctypes.c_void_p(-1).value)
threading.Thread(target=lambda:threading.Event().wait(60),daemon=False).start()
sys.frozen=True
finish_frozen_process()
'''
            result=subprocess.run([sys.executable,'-c',script,str(path)],cwd=Path(__file__).resolve().parents[1],
                                  timeout=5,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'));path.write_bytes(b'released')

if __name__=='__main__':unittest.main()
