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

from server16_py.startup_diagnostics import StartupSession, audit_files, file_evidence, version_info


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
                self.assertIn('mod_logs/server16.log',archive.namelist())
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
        info=version_info(sys.executable)
        self.assertIn('version',info)
        self.assertIn('sha256',file_evidence(sys.executable))

    def test_module_event_keeps_module_name_and_file_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            session=StartupSession(root/'report',os.getpid(),root/'fifa16.exe',{'files':[]},'test')
            module={'name':'python.exe','path':sys.executable,'base':'0x1000','image_bytes':1024}
            with patch('server16_py.startup_diagnostics.module_snapshot',return_value=[module]):
                session.capture_modules({})
            event=json.loads((root/'report/timeline.jsonl').read_text().splitlines()[0])
            self.assertEqual(event['event'],'module_loaded')
            self.assertEqual(event['name'],'python.exe')
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


if __name__=='__main__':unittest.main()
