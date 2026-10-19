import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.career_active_save import read_active_save, ActiveCareerUnavailable
import test_career_overlay as fixtures


class ActiveCareerIdentityTests(unittest.TestCase):
    def bridge(self, root, slot='abc', kind=b'SaveType_Career\0', **changes):
        path=root/'saves'/slot/'DATA';path.parent.mkdir(parents=True,exist_ok=True)
        data=bytearray(fixtures.container());data[116:132]=kind;path.write_bytes(data)
        (path.parent/'INDEX').touch()
        runtime=root/'ModCarrerMode/runtime';runtime.mkdir(parents=True,exist_ok=True)
        values=dict(schema=3,pid=123,process_created_100ns=999,save_type='SaveType_Career',
                    complete_file=1,operation='read',size_bytes=len(data),path=str(path))
        values.update(changes)
        (runtime/'career_save_source.tsv').write_text('\n'.join(f'{k}={v}' for k,v in values.items()))
        return path

    @patch('server16_py.career_active_save.process_created',return_value=999)
    def test_reads_current_process_completed_career_not_newest_file(self, _):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);active=self.bridge(root)
            newer=root/'saves/newer/DATA';newer.parent.mkdir();newer.write_bytes(fixtures.container(1))
            memory=SimpleNamespace(process_id=123)
            self.assertEqual(Path(read_active_save(root,memory)['path']),active)

    @patch('server16_py.career_active_save.process_created',return_value=999)
    def test_wrong_pid_creation_preview_legacy_and_settings_are_rejected(self, _):
        cases=[{'pid':124},{'process_created_100ns':998},{'schema':2},{'complete_file':0},
               {'size_bytes':1},{'operation':'preview'},{'kind':b'SaveType_Settin\0'},
               {'save_type':'SaveType_Settings'}]
        for changes in cases:
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);self.bridge(root,**changes)
                with self.assertRaises(ActiveCareerUnavailable):
                    read_active_save(root,SimpleNamespace(process_id=123))


class AutomaticCareerPanelTests(unittest.TestCase):
    def ready(self,root):
        return fixtures.CareerOverlayTests().make_ready(root)

    def test_loading_hides_partial_data_until_the_active_save_is_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.ready(Path(temporary));svc=selector.career_service
            selected,inspection=svc.selected,svc.inspection
            try:
                svc.selected=svc.inspection=None;svc.busy=True
                selector.open(career=True);panel=selector.career_panel
                panel.page='clubs'
                self.assertEqual(panel.data_gate(),'loading')
                self.assertEqual([r[0] for r in panel.items()],['Fechar'])
                with patch('server16_py.career_panel.OverlayDraw.text',autospec=True) as text:
                    panel.render()
                captions=[call.args[2] for call in text.call_args_list]
                self.assertIn('Carregando dados da carreira…',captions)
                self.assertFalse(any('Indisponível' in label or '0 de 0' in label for label in captions))
                panel.handle(3,0);panel.handle(10,ord('7'))
                self.assertIsNone(panel.country);self.assertEqual(panel.amount,'')
                self.assertIsNone(svc.pending)
                svc.selected=selected
                self.assertEqual(panel.data_gate(),'loading')
                svc.inspection=inspection;svc.busy=False;svc.state='ready';svc.revision+=1
                panel.tick()
                self.assertIsNone(panel.data_gate())
                self.assertEqual([r[0] for r in panel.items()][:3],['País / região','Liga / divisão','Time'])
                panel.activate(0);self.assertEqual(panel.country,14)
                panel.activate(1);self.assertEqual(panel.league,13)
                panel.activate(2);self.assertEqual(panel.team,2)
                panel.back();panel.activate(1);self.assertEqual(panel.page,'finances')
                self.assertIn('1.300.000',panel.items()[0][1])
            finally:selector.shutdown()

    def test_loading_animation_refreshes_without_service_events_and_allows_close(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.ready(Path(temporary));svc=selector.career_service
            try:
                svc.inspection=None;svc.busy=True
                selector.open(career=True);panel=selector.career_panel
                with patch.object(selector,'render') as render, patch('server16_py.career_panel.time.monotonic',return_value=10):
                    panel.tick();render.assert_called_once()
                    panel.tick();self.assertEqual(render.call_count,1)
                with patch.object(selector,'render') as render, patch('server16_py.career_panel.time.monotonic',return_value=10.3):
                    panel.tick();render.assert_called_once()
                panel.handle(7,0)
                self.assertIsNone(selector.career_panel)
            finally:selector.shutdown()

    def test_loading_returns_during_save_refresh_and_errors_do_not_spin_forever(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.ready(Path(temporary));svc=selector.career_service
            try:
                selector.open(career=True);panel=selector.career_panel
                panel.activate(1);panel.activate(0)
                svc.inspection=None;svc.busy=True;svc.state='loading'
                self.assertEqual(panel.data_gate(),'loading')
                svc.busy=False;svc.state='error';svc.message='Falha ao ler o save.'
                self.assertEqual(panel.data_gate(),'error')
                with patch('server16_py.career_panel.OverlayDraw.text',autospec=True) as text:
                    panel.render()
                captions=[call.args[2] for call in text.call_args_list]
                self.assertIn('Não foi possível carregar a carreira.',captions)
                self.assertIn(svc.message,captions)
                self.assertNotIn('Carregando dados da carreira…',captions)
                svc.pending={'action':'funds'};panel.page='status'
                self.assertIsNone(panel.data_gate())
            finally:selector.shutdown()

    def test_mouse_and_controller_open_both_actions_without_save_picker(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.ready(Path(temporary))
            try:
                selector.open(career=True);panel=selector.career_panel
                panel.handle(8,50|(130<<16));self.assertEqual(panel.page,'clubs')
                panel.back();panel.focus=1;panel.handle(6,0)
                self.assertEqual(panel.page,'finances');panel.handle(6,0)
                self.assertEqual(panel.page,'funds')
            finally:selector.shutdown()

    def test_automatically_inspects_bridge_and_refuses_changed_live_club(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.ready(Path(temporary));svc=selector.career_service
            try:
                selected=dict(svc.selected);inspection=dict(svc.inspection)
                svc.active_save=Mock(return_value=selected)
                svc.selected=svc.inspection=None
                with patch.object(svc,'_job',return_value=True) as job:
                    svc.sync_active();job.assert_called_once()
                    self.assertEqual(svc.selected['path'],selected['path'])
                svc.events.put(('inspect',svc.generation,inspection,None));svc.tick()
                self.assertIsNotNone(svc.inspection)
                svc.context_reader.profile=Mock(return_value={'userid':0,'club_id':999})
                with self.assertRaisesRegex(ValueError,'mudou'):svc.confirm('funds',amount=10)
                self.assertIsNone(svc.pending)
            finally:selector.shutdown()

    def test_autosave_or_save_as_change_requires_fresh_inspection(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.ready(Path(temporary));svc=selector.career_service
            try:
                changed=dict(svc.selected,mtime_ns=svc.selected['mtime_ns']+1)
                svc.active_save=Mock(return_value=changed)
                with self.assertRaisesRegex(ValueError,'progresso mudou'):svc.confirm('funds',amount=10)
                self.assertIsNone(svc.pending);self.assertIsNone(svc.inspection)
                with patch.object(svc,'_job',return_value=True) as job:
                    svc.sync_active();job.assert_called_once()
                    self.assertEqual(svc.selected['mtime_ns'],changed['mtime_ns'])
            finally:selector.shutdown()

    def test_confirmation_cannot_follow_a_different_career_automatically(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.ready(Path(temporary));svc=selector.career_service
            try:
                selector.open(career=True);panel=selector.career_panel
                panel.activate(1);panel.activate(0);panel.digit('9');panel.activate(12)
                self.assertEqual(panel.page,'confirm')
                svc.generation+=1;panel.activate(0)
                self.assertEqual(panel.page,'funds');self.assertIsNone(svc.pending)
                self.assertIn('atualizada',panel.message)
            finally:selector.shutdown()

    def test_applied_notice_survives_detection_when_back_at_main_menu(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.ready(Path(temporary));svc=selector.career_service
            try:
                selector.app.lastpagename='game/screens/mainMenu/MainMenu'
                svc.state='done';svc.message='Aplicado com backup.';svc.inspection=None
                svc.tick()
                self.assertEqual(svc.state,'done');self.assertEqual(svc.message,'Aplicado com backup.')
            finally:selector.shutdown()


if __name__=='__main__':unittest.main()
