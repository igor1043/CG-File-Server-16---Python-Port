import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_stadium_selector as fixtures
from server16_py.career_save_worker import blocks, fingerprint
from server16_py.career_service import CareerService, career_page, safe_exit_page, publish_save
from server16_py.career_panel import CareerPanel


def container(fill=0):
    data=bytearray(160)
    data[116:132]=b'SaveType_Career\0'
    struct.pack_into('<I',data,136,56)
    for _ in range(3):
        data += b'DB\x00\x08'+struct.pack('<4I',0,28,0,1)+bytes([fill])*8
    struct.pack_into('<I',data,132,zlib.crc32(data[160:]))
    return bytes(data)


def catalog():
    return {'nations':{'54':'Brasil','14':'Inglaterra'},'nation_codes':{'54':'br','14':'gb'},
            'leagues':[{'id':13,'name':'Premier League','country_id':14,'level':1},
                       {'id':350,'name':'Série D','country_id':54,'level':4}],
            'teams':[{'id':1,'name':'Arsenal','asset_id':1},
                     {'id':2,'name':'Clube B','asset_id':2},
                     {'id':130190,'name':'Anápolis','asset_id':130190}],
            'links':[[13,1],[13,2],[350,130190]]}


class CareerSaveTests(unittest.TestCase):
    def test_supported_container_rejects_corrupt_or_unknown_layout(self):
        self.assertEqual(blocks(container()),[(160,28),(188,28),(216,28)])
        invalid=bytearray(container());invalid[-1]^=1
        with self.assertRaisesRegex(ValueError,'integridade'):blocks(invalid)
        invalid=bytearray(container());invalid[136]=0
        with self.assertRaisesRegex(ValueError,'Formato'):blocks(invalid)

    def test_publication_preserves_index_and_creates_exact_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);slot=root/'slot';slot.mkdir()
            path=slot/'DATA';path.write_bytes(container())
            index=slot/'INDEX';index.write_bytes(b'original index metadata')
            backup=Path(publish_save(path,fingerprint(container()),container(1),root/'backups'))
            self.assertEqual(path.read_bytes(),container(1))
            self.assertEqual(index.read_bytes(),b'original index metadata')
            self.assertEqual((backup/'DATA').read_bytes(),container())
            self.assertEqual((backup/'INDEX').read_bytes(),index.read_bytes())
            receipt=json.loads((backup/'receipt.json').read_text())
            self.assertEqual(receipt['after'],fingerprint(path.read_bytes()))

    def test_modified_save_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'DATA';path.write_bytes(container(1));(root/'INDEX').touch()
            with self.assertRaisesRegex(ValueError,'mudou'):
                publish_save(path,fingerprint(container()),container(2),root/'backups')
            self.assertEqual(path.read_bytes(),container(1))
            self.assertFalse((root/'backups').exists())


class CareerOverlayTests(unittest.TestCase):
    def test_page_signal_excludes_matches_and_unknown_exit_pages(self):
        self.assertTrue(career_page('game/screens/career/CareerHub'))
        for page in ('','InGame','game/screens/career/PreMatchHub','game/screens/career/TeamSelect',
                     'game/screens/mainMenu/MainMenu'):
            self.assertFalse(career_page(page))
        self.assertTrue(safe_exit_page('game/screens/mainMenu/MainMenu'))
        for page in ('','InGame','game/screens/career/Home','game/screens/playNow/KickOffHub'):
            self.assertFalse(safe_exit_page(page))

    def make_ready(self,root):
        selector=fixtures.StadiumSelectorTests().make_selector(root)
        app=selector.app;app.exedir=root/'game';app.lastpagename='game/screens/career/Home'
        svc=selector.career_service;svc.catalog=catalog();svc.state='ready'
        svc.feedback=Mock()
        svc.jobs_runtime=Mock()
        svc.jobs_runtime.ready.return_value=False
        svc.jobs_runtime.poll.return_value=None
        svc.jobs_runtime.request.return_value=1
        svc.jobs_runtime.pid=1234
        svc.jobs_runtime.shared=SimpleNamespace(load_epoch=1)
        slot=root/'slot';slot.mkdir();(slot/'DATA').write_bytes(container());(slot/'INDEX').touch()
        svc.saves=[{'title':'Minha carreira','path':str(slot/'DATA'),'slot':'slot','modified':1}]
        svc.selected=svc.saves[0]
        stat=(slot/'DATA').stat()
        svc.selected.update(pid=1234,process_created_100ns=123456,size=stat.st_size,mtime_ns=stat.st_mtime_ns)
        svc.inspection={'context':{'userid':0,'club_id':130190,'club':'Anápolis','player_id':None,
                                  'budget':1_300_000,'currency':0},
                        'fingerprint':fingerprint(container()),'catalog':catalog()}
        svc.active_save=Mock(side_effect=lambda:dict(svc.selected))
        svc.context_reader.profile=Mock(side_effect=lambda **_: dict({
            key:svc.inspection['context'][key] for key in ('userid','club_id')},job_offer_protocol=1)
            if svc.inspection else {'userid':0,'club_id':130190})
        return selector

    def test_career_shortcut_opens_stadium_settings_and_retains_career_tools(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary))
            try:
                selector.shared.ready=7;selector._attempted_pid=1234
                selector.shared.events[0].kind=1;selector.shared.write_index=1
                selector.tick()
                self.assertEqual(selector.shared.enabled,3)
                self.assertIsNotNone(selector.frontend_panel)
                self.assertTrue(selector._frontend_career)
                self.assertIn(3,[i for i,r in selector.frontend_panel.targets()])
                selector.frontend_panel.activate(3)
                self.assertIsInstance(selector.career_panel,CareerPanel)
                self.assertIsNone(selector.audio_panel)
                self.assertIsNone(selector.prematch_panel)
                selector.app.lastpagename='InGame';selector.tick()
                self.assertIsNone(selector.career_panel)
            finally:selector.shutdown()

    def test_funds_keyboard_confirmation_and_cancel_do_not_write_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary))
            try:
                selector.open(career=True);panel=selector.career_panel
                panel.activate(1);self.assertEqual(panel.page,'finances')
                panel.activate(0)
                for character in '12500000':panel.handle(10,ord(character))
                self.assertEqual(panel.amount,'12500000')
                panel.handle(16,1);self.assertEqual(panel.page,'confirm')
                self.assertEqual(panel.focus,1)  # Review starts with Back selected.
                self.assertIsNone(selector.career_service.pending)
                panel.activate(0)
                svc=selector.career_service
                self.assertEqual(svc.pending['amount'],12_500_000)
                self.assertEqual(svc.state,'waiting_exit')
                self.assertEqual(Path(svc.pending['path']).read_bytes(),container())
                self.assertIsNone(selector.career_panel)
                selector.open(career=True);panel=selector.career_panel
                panel.activate(0)
                self.assertIsNone(svc.pending)
                self.assertFalse((svc.root/'pending.json').exists())
            finally:selector.shutdown()

    def test_catalog_filters_and_confirmation_bind_team_league_and_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary))
            try:
                selector.open(career=True);panel=selector.career_panel
                panel.activate(0);self.assertEqual(panel.page,'clubs')
                panel.country=14;panel.reset_filters()
                self.assertEqual(panel.league,13)
                self.assertEqual([r['id'] for r in panel.teams()],[1,2])
                panel.activate(3)
                with patch('server16_py.competition_catalog.nodes',return_value={323:(3,'C13','Name',319)}):
                    panel.activate(0)
                pending=selector.career_service.pending
                self.assertEqual(pending['action'],'live_job')
                self.assertIsNone(selector.career_panel)
                self.assertEqual((pending['team_id'],pending['league_id']),(1,13))
                self.assertEqual(pending['path'],selector.career_service.selected['path'])
            finally:selector.shutdown()

    def test_feedback_lifecycle_only_reports_done_after_verified_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc.confirm('funds',amount=100)
                self.assertEqual(svc.feedback.show.call_args.args[0],'prepared')
                token=svc.pending['request_id']
                svc.busy=True
                svc.events.put(('prepare',None,None,'falha na ponte'))
                svc.tick()
                self.assertEqual(svc.feedback.show.call_args.args[0],'error')
                self.assertIsNotNone(svc.pending)
                self.assertEqual(Path(svc.pending['path']).read_bytes(),container())
                selector.app.lastpagename='game/screens/mainMenu/MainMenu'
                (svc.root/'prepared_DATA').write_bytes(container(1))
                svc.events.put(('prepare',None,{'context':{'budget':1300100}},None))
                svc.tick()
                self.assertEqual(svc.state,'done')
                self.assertIsNone(svc.pending)
                self.assertEqual(Path(svc.selected['path']).read_bytes(),container(1))
                self.assertEqual(svc.feedback.show.call_args.args[0],'done')
                self.assertEqual(svc.feedback.show.call_args.args[2],token)
            finally:selector.shutdown()

    def test_waits_for_safe_exit_and_rechecks_page_after_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc.confirm('funds',amount=100)
                with patch.object(svc,'_job') as job, patch('server16_py.career_service.time.monotonic',return_value=10):
                    svc.tick();job.assert_not_called()
                    selector.app.lastpagename='';svc.tick();job.assert_not_called()
                    selector.app.lastpagename='game/screens/mainMenu/MainMenu';svc.tick();job.assert_not_called()
                with patch.object(svc,'_job',return_value=True) as job, patch('server16_py.career_service.time.monotonic',return_value=13):
                    svc.tick();job.assert_called_once()
                svc.busy=True
                selector.app.lastpagename='game/screens/career/Home'
                svc.events.put(('prepare',None,{'context':{}},None))
                with patch('server16_py.career_service.publish_save') as publish:
                    svc.tick();publish.assert_not_called()
                self.assertEqual(svc.state,'waiting_exit')
                self.assertIsNotNone(svc.pending)
            finally:selector.shutdown()

    def test_reopening_too_soon_keeps_preparation_and_finishes_on_next_safe_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc.confirm('funds',amount=100)
                original=Path(svc.pending['path'])
                (svc.root/'prepared_DATA').write_bytes(container(1))
                result={'context':dict(svc.pending['context'],budget=1300100)}
                svc.busy=True
                svc.events.put(('prepare',None,result,None))
                svc.tick()
                self.assertEqual(svc.state,'waiting_exit')
                self.assertEqual(svc.feedback.show.call_args.args[0],'waiting_exit')
                self.assertEqual(original.read_bytes(),container())
                selector.app.lastpagename='game/screens/mainMenu/MainMenu'
                with patch.object(svc,'_job') as worker,patch('server16_py.career_service.time.monotonic',return_value=10):
                    svc.tick();worker.assert_not_called()
                with patch.object(svc,'_job') as worker,patch('server16_py.career_service.time.monotonic',return_value=13):
                    svc.tick();worker.assert_not_called()
                    svc.tick();worker.assert_not_called()
                self.assertEqual(svc.state,'done')
                self.assertEqual(original.read_bytes(),container(1))
                self.assertEqual(svc.feedback.show.call_args.args[0],'done')
                self.assertTrue((svc.root/'last_applied.json').is_file())
            finally:selector.shutdown()

    def test_completion_notice_is_not_emitted_if_prepared_payload_changed(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc.confirm('funds',amount=100)
                original=Path(svc.pending['path'])
                selector.app.lastpagename='game/screens/mainMenu/MainMenu'
                (svc.root/'prepared_DATA').write_bytes(container(2))
                svc.busy=True
                svc.events.put(('prepare',None,{'context':{},'output_sha256':fingerprint(container(1))},None))
                svc.tick()
                self.assertEqual(svc.state,'error')
                self.assertIsNotNone(svc.pending)
                self.assertEqual(original.read_bytes(),container())
                self.assertEqual(svc.feedback.show.call_args.args[0],'error')
                self.assertFalse((svc.root/'last_applied.json').exists())
            finally:selector.shutdown()

    def test_player_career_rejects_club_budget_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc.inspection['context']['player_id']=56027
                with self.assertRaisesRegex(ValueError,'treinador'):svc.confirm('funds',amount=100)
                self.assertIsNone(svc.pending)
            finally:selector.shutdown()

    def test_manager_offer_requires_live_runtime_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc.jobs_runtime.request.side_effect=ValueError('Preparando as vagas em memória.')
                with self.assertRaisesRegex(ValueError,'Preparando'):svc.confirm('transfer',team_id=1,league_id=13)
                self.assertIsNone(svc.pending)
            finally:selector.shutdown()

    def test_live_request_waits_for_native_ack_then_accepts_a_second_club_without_editing_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                source=Path(svc.selected['path']);original=source.read_bytes()
                svc.jobs_runtime.request.side_effect=[1,2]
                svc.confirm('transfer',team_id=1,league_id=13)
                self.assertEqual(svc.pending['action'],'live_job')
                svc.tick()
                self.assertEqual(svc.state,'waiting_runtime')
                self.assertFalse((svc.root/'last_live_applied.json').exists())
                result={'team_id':1,'league_id':13,'proposals':[[1,13]],'save_edited':False,
                        'proposal_received':True,'native_contract_queued':True,'valid_for_days':3}
                svc.jobs_runtime.poll.return_value=result
                with patch('server16_py.career_service.publish_save') as publish,patch('server16_py.career_service.run_worker') as worker:
                    svc.tick();publish.assert_not_called();worker.assert_not_called()
                self.assertIsNone(svc.pending)
                self.assertEqual(svc.feedback.show.call_args.args[0],'done')
                self.assertIn('Aceite ou recuse no contrato do FIFA',svc.feedback.show.call_args.args[1])
                self.assertNotIn('candidate-se',svc.feedback.show.call_args.args[1])
                self.assertIn('3 dias de jogo',svc.feedback.show.call_args.args[1])
                self.assertEqual(source.read_bytes(),original)
                svc.confirm('transfer',team_id=2,league_id=13)
                self.assertEqual(svc.pending['ticket'],2)
                svc.jobs_runtime.poll.return_value=dict(result,team_id=2,proposals=[[2,13]])
                svc.tick()
                self.assertIsNone(svc.pending)
                self.assertEqual(source.read_bytes(),original)
                self.assertEqual(len(json.loads((svc.root/'live_jobs.json').read_text())),2)
            finally:selector.shutdown()

    def test_native_rejection_reports_error_without_a_completion_notice_or_save_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                source=Path(svc.selected['path']);original=source.read_bytes()
                svc.confirm('transfer',team_id=1,league_id=13)
                svc.jobs_runtime.poll.side_effect=ValueError('A carreira mudou.')
                svc.tick()
                self.assertIsNone(svc.pending)
                self.assertEqual(svc.feedback.show.call_args.args[0],'error')
                self.assertEqual(source.read_bytes(),original)
            finally:selector.shutdown()

    def test_changing_career_during_delivery_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc.confirm('transfer',team_id=1,league_id=13)
                svc.jobs_runtime.shared.load_epoch=2
                svc._poll_live_request()
                self.assertIsNone(svc.pending)
                self.assertEqual(svc.state,'error')
                self.assertEqual(svc.feedback.show.call_args.args[0],'error')
                svc.jobs_runtime.poll.assert_not_called()
            finally:selector.shutdown()

    def test_receipt_history_never_reapplies_refused_or_expired_proposals(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc._live_history=[{'team_id':1,'league_id':13,'path':svc.selected['path'],
                                    'context':svc.inspection['context']}]
                svc.restore_live_vacancies()
                svc.jobs_runtime.request.assert_not_called()
                self.assertIsNone(svc.pending)
            finally:selector.shutdown()

    def test_background_preload_starts_before_panel_open_and_runs_catalog_and_save_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                selected=dict(svc.selected);svc.catalog=svc.selected=svc.inspection=None
                svc.active_save=Mock(return_value=selected)
                with patch('server16_py.career_service.threading.Thread') as thread:
                    svc.tick()
                    self.assertEqual(thread.call_count,2)
                    self.assertEqual(svc._inflight,{'catalog','inspect'})
                    self.assertTrue(svc.busy)
                    self.assertIsNone(selector.career_panel)
                svc.events.put(('catalog',None,catalog(),None));svc.tick()
                self.assertTrue(svc.busy)
                self.assertEqual(svc._inflight,{'inspect'})
            finally:selector.shutdown()

    def test_completion_does_not_automatically_open_the_panel(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                svc.state='done';svc._notice_until=10**20
                selector._attempted_pid=1234;selector.shared.ready=7
                with patch.object(selector,'open') as opened:selector.tick();opened.assert_not_called()
                self.assertIsNone(selector.career_panel)
            finally:selector.shutdown()

    def test_publication_gate_reads_ram_again_and_rejects_lost_attachment(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary));svc=selector.career_service
            try:
                selector.app.lastpagename='game/screens/mainMenu/MainMenu'
                selector.app.offsets=SimpleNamespace(ORIPGBASE=1,PG1=[2])
                selector.app.memory.get_string=Mock(return_value='game/screens/career/Home')
                self.assertFalse(svc.safe_to_apply())
                selector.app.memory.get_string.return_value='game/screens/mainMenu/MainMenu'
                self.assertTrue(svc.safe_to_apply())
                selector.app.memory.get_string.side_effect=RuntimeError('lost read')
                self.assertFalse(svc.safe_to_apply())
                selector.app.memory.is_open=lambda:False
                self.assertFalse(svc.safe_to_apply())
                selector.app._resolve_fifa_pid=lambda:0
                self.assertTrue(svc.safe_to_apply())
            finally:selector.shutdown()

    def test_all_pages_render_for_keyboard_and_controller(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=self.make_ready(Path(temporary))
            try:
                selector.open(career=True);panel=selector.career_panel
                for page in ('home','clubs','finances','funds','confirm','status'):
                    panel.page=page;panel.confirmation={'return':'funds','action':'funds','amount':100,'label':'100'}
                    for controller in (False,True):
                        selector.controller_connected=controller
                        image=panel.render()
                        self.assertEqual(image.size,(1200,1360))
            finally:selector.shutdown()


if __name__=='__main__':unittest.main()
