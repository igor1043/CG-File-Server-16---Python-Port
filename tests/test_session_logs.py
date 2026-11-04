import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py import session_logs as logs


class SessionLogTests(unittest.TestCase):
    def file(self,root,relative,data=b'old evidence\n'):
        p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p

    def test_reset_reaches_server_native_mod_and_worker_logs_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            managed=[self.file(root,p) for p in ('runtime/server16.log','runtime/server16.previous.log',
                'ModCarrerMode/logs/mascot.log','ModCarrerMode/runtime/club_browser/18/service.log',
                'ModCarrerMode/runtime/club_environment/room/runtime/native_room.log',
                'ModCarrerMode/data/bank/worker.log.1','ModCarrerMode/mods/camera/trace.log','dinput8_L9.log',
                'ModCarrerMode/crowd_attendance_runtime.log','bin/overlay.log')]
            preserved=[self.file(root,p) for p in ('ModCarrerMode/runtime/career.json','runtime/settings.json',
                'ModCarrerMode/data/bank/state.sqlite3','ModCarrerMode/data/room/profile.json',
                'ModCarrerMode/runtime/native_components_v2.txt','data/player.rx3','FSW/settings.ini',
                'saves/Career','ModCarrerMode/source/test.log','local-review/study.log')]
            report=logs.maintain(root,reset=True)
            self.assertEqual(report.files,len(managed));self.assertFalse(report.failed)
            self.assertTrue(all(p.read_bytes()==b'' for p in managed))
            self.assertTrue(all(p.read_bytes()==b'old evidence\n' for p in preserved))

    def test_trims_tail_and_total_without_reading_whole_large_log(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);large=self.file(root,'ModCarrerMode/logs/large.log',b'prefix\n'*100+b'last good event\n')
            second=self.file(root,'runtime/worker.log',b'keep\n'*10)
            report=logs.maintain(root,file_limit=100,tail_bytes=32,total_limit=100)
            self.assertGreater(report.freed,500);self.assertLessEqual(large.stat().st_size,32)
            self.assertTrue(large.read_bytes().endswith(b'last good event\n'));self.assertEqual(second.read_bytes(),b'keep\n'*10)
            self.file(root,'runtime/other.log',b'x'*80)
            logs.maintain(root,file_limit=100,total_limit=60)
            self.assertLessEqual(sum(p.stat().st_size for p in logs.log_files(root)),60)

    def test_persistent_append_writer_keeps_working_after_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=self.file(root,'runtime/worker.log')
            with p.open('ab') as stream:
                logs.maintain(root,reset=True);stream.write(b'new session\n');stream.flush()
            self.assertEqual(p.read_bytes(),b'new session\n')

    def test_busy_file_does_not_abort_other_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);busy=self.file(root,'runtime/busy.log');other=self.file(root,'runtime/other.log')
            original=Path.open
            def opened(path,*args,**kw):
                if path==busy and args and args[0]=='r+b':raise PermissionError('busy')
                return original(path,*args,**kw)
            with patch.object(Path,'open',opened):report=logs.maintain(root,reset=True)
            self.assertEqual(len(report.failed),1);self.assertEqual(other.read_bytes(),b'')
            self.assertEqual(busy.read_bytes(),b'old evidence\n')

    def test_links_cannot_escape_scope_or_modify_a_shared_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'game';root.mkdir();outside=Path(folder)/'outside';outside.mkdir()
            source=self.file(outside,'other.log');hard=root/'shared.log';os.link(source,hard)
            try:os.symlink(outside,root/'runtime',target_is_directory=True)
            except OSError:pass
            report=logs.maintain(root,reset=True)
            self.assertFalse(report.failed);self.assertEqual(source.read_bytes(),b'old evidence\n')
            self.assertFalse(logs.safe(root,outside/'other.log'))
            self.assertFalse(logs.safe(Path(root.anchor),root))

    def test_old_diagnostic_bundles_clean_but_active_and_unknown_files_stay(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);name='20260101_120000_000001_pid18'
            old=self.file(root,'runtime/diagnostics/'+name+'/logs/native.log')
            archive=self.file(root,'runtime/diagnostics/'+name+'.zip')
            active=root/'runtime/diagnostics/20260102_120000_000001_pid19'
            active_log=self.file(root,str(active.relative_to(root))+'/timeline.jsonl')
            user=self.file(root,'runtime/diagnostics/my-notes.txt')
            logs.maintain(root,reset=True,protected=(active,))
            self.assertFalse(old.exists());self.assertFalse(archive.exists())
            self.assertTrue(active_log.exists());self.assertEqual(user.read_bytes(),b'old evidence\n')

    def test_new_diagnostic_created_after_startup_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cutoff=time.time()-10
            p=self.file(root,'runtime/diagnostics/20260101_120000_000001_pid18/summary.json')
            logs.maintain(root,reset=True,cutoff=cutoff);self.assertTrue(p.exists())
            logs.maintain(root,diagnostics_limit=1);self.assertFalse(p.exists())

    def test_background_startup_clear_button_and_periodic_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=self.file(root,'runtime/worker.log');done=threading.Event();calls=[]
            service=logs.SessionLogs(interval=.02)
            try:
                service.bind(root);service.bind(root)
                def callback(report):calls.append((threading.get_ident(),report));done.set()
                service.clear(callback);self.assertTrue(done.wait(3));self.assertEqual(p.read_bytes(),b'')
                self.assertNotEqual(calls[0][0],threading.get_ident());self.assertEqual(len(service.roots),1)
                p.write_bytes(b'x'*(logs.FILE_LIMIT+1))
                deadline=time.monotonic()+3
                while p.stat().st_size>logs.TAIL_BYTES and time.monotonic()<deadline:time.sleep(.02)
                self.assertLessEqual(p.stat().st_size,logs.TAIL_BYTES)
            finally:service.close()
            self.assertFalse(service.thread.is_alive())

    def test_app_clear_button_uses_same_service_and_does_not_delete_state(self):
        from server16_py.app import Server16App
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=self.file(root,'runtime/server16.log');state=self.file(root,'runtime/settings.json')
            app=SimpleNamespace(clear_logs_button=Mock(),_log_lock=threading.Lock(),log_widget=Mock(),_log_ui_lines=100,
                _prepare_runtime_log=lambda:p.write_text('header\n'),_session_logs=Mock(),log=Mock(),tr=lambda key,**kw:key,
                _post_ui=Mock(),_finish_clear_logs=Mock())
            Server16App._clear_session_logs(app)
            self.assertEqual(p.read_text(),'header\n');self.assertEqual(app._log_ui_lines,0)
            callback=app._session_logs.clear.call_args.args[0];callback(logs.Result(files=3,freed=100))
            app.log.assert_called_once();app._post_ui.assert_called_once()
            self.assertEqual(state.read_bytes(),b'old evidence\n')


if __name__=='__main__':unittest.main()
