import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace
import zipfile

from server16_py.startup_diagnostics import (StartupSession, StartupDiagnostics, audit_files,
                                           file_evidence, version_info, log_marker, session_log, crash_summary)


class StartupDiagnosticsTests(unittest.TestCase):
    def test_exact_hash_missing_divergent_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'same.big').write_bytes(b'same')
            (root/'changed.big').write_bytes(b'changed')
            expected=hashlib.sha256(b'same').hexdigest()
            reference={'files':[{'path':name,'sha256':expected} for name in
                ('same.big','changed.big','missing.big','../outside','C:/outside')]}
            rows=audit_files(root,reference)
            self.assertEqual([r['status'] for r in rows],
                             ['match','different','missing','invalid_reference','invalid_reference'])
            self.assertEqual(rows[1]['actual']['sha256'],hashlib.sha256(b'changed').hexdigest())

    def test_mod_junction_targets_are_legitimate_read_only_files(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as destination:
            root=Path(directory); linked=root/'mods'; target=Path(destination)
            (target/'test.dll').write_bytes(b'plugin')
            command=subprocess.run(['cmd','/c','mklink','/J',str(linked),str(target)],
                                   capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(command.returncode,0,command.stderr)
            reference={'files':[{'path':'mods/test.dll','sha256':hashlib.sha256(b'plugin').hexdigest()}]}
            self.assertEqual(audit_files(root,reference)[0]['status'],'match')
            self.assertEqual((target/'test.dll').read_bytes(),b'plugin')
            os.rmdir(linked)  # Remove only the fixture junction, never its target.

    def test_page_history_and_archive_exclude_settings_and_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'runtime').mkdir()
            (root/'runtime/settings.json').write_text('secret fixture')
            (root/'runtime/server16.log').write_text('server evidence')
            session=StartupSession(root/'report',123,root/'fifa16.exe',{'files':[]},'test')
            for _ in range(45): session.page_seen(error='not initialized')
            session.page_seen(page='game/screens/bootflow/PressStart')
            session.page_seen(page='game/screens/saveload_pc/bootload')
            session.finish()
            events=[json.loads(line) for line in (root/'report/timeline.jsonl').read_text().splitlines()]
            self.assertEqual([e['attempts'] for e in events if e['event']=='page_read_pending'],[1,20,40])
            self.assertEqual(events[-2]['pending_reads'],45)
            self.assertEqual(session.state['last_page'],'game/screens/saveload_pc/bootload')
            with zipfile.ZipFile(root/'report.zip') as archive:
                self.assertIn('logs/server/server16.log',archive.namelist())
                self.assertEqual(archive.read('logs/server/server16.log'),b'')  # Content before attach belongs to an earlier session.
                self.assertFalse(any('settings' in name or 'save' in name for name in archive.namelist()))
                self.assertIn('referência ausente',archive.read('LEIA-ME.txt').decode())

    @unittest.skipUnless(os.name=='nt','Windows process exit observer')
    def test_real_child_exit_is_observed_even_when_server_closes_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(1);raise SystemExit(37)'],
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            session=StartupSession(root/'report',child.pid,root/'fifa16.exe',{'files':[]},'test')
            with patch('server16_py.startup_diagnostics.module_snapshot',return_value=[]):
                session.thread.start()
                try:
                    self.assertEqual(child.wait(timeout=5),37)
                    session.stopped.set()
                    session.thread.join(5)
                    self.assertFalse(session.thread.is_alive())
                    self.assertEqual(session.state['exit_code'],'0x00000025')
                    self.assertEqual(session.state['status'],'process_exit_observed')
                    self.assertTrue((root/'report.zip').is_file())
                finally:
                    if child.poll() is None:
                        child.terminate(); child.wait(timeout=3)

    def test_windows_file_version_is_read_without_loading_game_dll(self):
        binary=Path(os.environ['WINDIR'])/'System32/kernel32.dll'
        info=version_info(binary)
        self.assertIn('version',info)
        self.assertIn('sha256',file_evidence(binary))

    def test_module_event_keeps_module_name_and_file_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            session=StartupSession(root/'report',os.getpid(),root/'fifa16.exe',{'files':[]},'test')
            module={'name':'kernel32.dll','path':str(Path(os.environ['WINDIR'])/'System32/kernel32.dll'),'base':'0x1000','image_bytes':1024}
            with patch('server16_py.startup_diagnostics.module_snapshot',return_value=[module]):
                session.capture_modules({})
            event=json.loads((root/'report/timeline.jsonl').read_text().splitlines()[0])
            self.assertEqual(event['event'],'module_loaded')
            self.assertEqual(event['name'],'kernel32.dll')
            self.assertIn('version',event)

    def test_app_pending_reader_is_counted_and_recovery_preserves_transition(self):
        from server16_py.app import Server16App
        page='game/screens/saveload_pc/bootload'
        app=SimpleNamespace(memory=SimpleNamespace(get_string=Mock(side_effect=[RuntimeError('not initialized')]*25+[page])),
            offsets=SimpleNamespace(ORIPGBASE=1,PG1=[2]),_startup_diagnostics=Mock(),
            _sync_page_banner=Mock(),_handle_page_transition=Mock(),
            _page_can_have_match_context=Mock(return_value=False),_set_process_status=Mock(),
            status_text=Mock(return_value='pending'),gold='gold',log=Mock())
        with patch('server16_py.app.time.monotonic',return_value=100):
            for _ in range(25):Server16App.update_page_name(app)
            self.assertEqual(app.log.call_count,1)
            Server16App.update_page_name(app)
        app._handle_page_transition.assert_called_once_with(page)
        self.assertEqual(app._page_read_pending,0)
        self.assertEqual(app.log.call_count,2)
        self.assertEqual(app._startup_diagnostics.page_seen.call_count,26)

    def test_only_appended_mod_records_are_collected_and_rotations_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'mod.log'
            path.write_bytes(b'old session\n');marker=log_marker(path)
            with path.open('ab') as stream:stream.write(b'new session\n')
            data,metadata=session_log(path,marker)
            self.assertEqual(data,b'new session\n')
            self.assertFalse(metadata['rotated_or_truncated'])
            path.write_bytes(b'new replacement file with a longer session\n')
            data,metadata=session_log(path,marker)
            self.assertEqual(data,path.read_bytes())
            self.assertTrue(metadata['rotated_or_truncated'])

    def test_each_launch_zeros_active_logs_and_collects_every_mod_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);mods=root/'ModCarrerMode/logs';mods.mkdir(parents=True)
            for name in ('cloth_motion.log','career_loader.log'):(mods/name).write_bytes(b'prior session')
            (mods/'settings.ini').write_bytes(b'preserve')
            diagnostics=StartupDiagnostics(root,root,'test',Mock())
            diagnostics.prepare_launch(root/'fifa16.exe')
            for path in mods.glob('*.log'):self.assertEqual(path.read_bytes(),b'')
            (mods/'cloth_motion.log').write_bytes(b'current cloth event')
            (mods/'career_loader.log').write_bytes(b'current loader event')
            session=StartupSession(root/'report',123,root/'fifa16.exe',{'files':[]},'test',diagnostics.pending_markers)
            (mods/'new_mod.log').write_bytes(b'current new mod event')
            session.finish()
            with zipfile.ZipFile(root/'report.zip') as archive:
                self.assertEqual(archive.read('logs/mods/cloth_motion.log'),b'current cloth event')
                self.assertEqual(archive.read('logs/mods/new_mod.log'),b'current new mod event')
                self.assertFalse(any(b'prior session' in archive.read(name) for name in archive.namelist()))
            diagnostics.prepare_launch(root/'fifa16.exe')
            for path in mods.glob('*.log'):self.assertEqual(path.read_bytes(),b'')
            self.assertEqual((mods/'settings.ini').read_bytes(),b'preserve')
            self.assertTrue((root/'report.zip').is_file())

    def test_crash_metadata_is_linked_by_pid_and_stale_dumps_are_excluded(self):
        import struct
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pid=123
            data=bytearray(120)
            struct.pack_into('<4sIIIIIQ',data,0,b'MDMP',0,2,32,0,0,0)
            struct.pack_into('<III',data,32,15,12,56)
            struct.pack_into('<III',data,44,6,40,68)
            struct.pack_into('<III',data,56,12,1,pid)
            struct.pack_into('<I',data,68+8,0xc0000005)
            struct.pack_into('<Q',data,68+24,0x12345678)
            session=StartupSession(root/'report',pid,root/'fifa16.exe',{'files':[]},'test')
            (root/'crash.dmp').write_bytes(data)
            (root/'old.dmp').write_bytes(data);os.utime(root/'old.dmp',(1,1))
            self.assertEqual(crash_summary(root/'crash.dmp')['exception_code'],'0xc0000005')
            session.finish()
            self.assertEqual(len(session.state['crash_dumps']),1)
            self.assertEqual(session.state['crash_dumps'][0]['association'],'matching_pid')
            with zipfile.ZipFile(root/'report.zip') as archive:
                self.assertEqual(archive.read('crash/crash.dmp'),data)
                self.assertNotIn('crash/old.dmp',archive.namelist())


if __name__=='__main__':unittest.main()
