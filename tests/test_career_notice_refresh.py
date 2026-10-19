import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_career_overlay as fixtures
from server16_py.career_panel import CareerPanel


class CareerNoticeRefreshTests(unittest.TestCase):
    def ready(self, root):
        selector = fixtures.CareerOverlayTests().make_ready(root)
        profile = {'userid':0, 'club_id':130190, 'career_role':1}
        svc = selector.career_service
        svc.context_reader.profile = Mock(side_effect=lambda **_:dict(profile))
        return selector, profile

    def finish_inspection(self, svc, result):
        svc.events.put(('inspect',svc.generation,result,None))
        svc.tick()

    def test_signature_updates_live_club_without_rereading_old_save_or_showing_old_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            selector,profile = self.ready(Path(temp));svc = selector.career_service
            try:
                disk = copy.deepcopy(svc.inspection)
                profile['club_id'] = 2
                self.finish_inspection(svc,disk)
                self.assertEqual(svc.inspection['context']['club'],'Clube B')
                self.assertEqual(svc.inspection['context']['club_id'],2)
                self.assertIsNone(svc.inspection['context']['budget'])
                self.assertFalse(svc.inspection['save_synced'])
                self.assertEqual(svc.state,'ready')
                generation = svc.generation
                with patch.object(svc,'_job') as job:
                    for _ in range(50):
                        svc._next_active_check = 0;svc.sync_active()
                    job.assert_not_called()
                self.assertEqual(svc.generation,generation)
                selector.open(career=True);panel = selector.career_panel
                self.assertIsNone(panel.data_gate())
                panel.page='finances'
                self.assertIn('Salve',panel.items()[0][1])
                panel.render()  # Unknown live budget must not reach money(None).
                panel.activate(0)
                self.assertEqual(panel.page,'finances')
                self.assertIn('Salve',panel.message)
                with self.assertRaisesRegex(ValueError,'Salve'):
                    svc.confirm('remove_retirement')
            finally:selector.shutdown()

    def test_new_save_is_read_once_and_restores_new_club_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            selector,profile = self.ready(Path(temp));svc = selector.career_service
            try:
                disk = copy.deepcopy(svc.inspection);profile['club_id']=2
                self.finish_inspection(svc,disk)
                changed = dict(svc.selected,mtime_ns=svc.selected['mtime_ns']+1)
                svc.active_save = Mock(return_value=changed)
                svc._next_active_check=0
                with patch.object(svc,'_job',return_value=True) as job:
                    svc.sync_active();job.assert_called_once()
                    updated=copy.deepcopy(disk)
                    updated['context'].update(club_id=2,club='Clube B',budget=29_000_000)
                    self.finish_inspection(svc,updated)
                    for _ in range(20):svc._next_active_check=0;svc.sync_active()
                    self.assertEqual(job.call_count,1)
                self.assertEqual(svc.inspection['context']['budget'],29_000_000)
                self.assertIsNot(svc.inspection.get('save_synced'),False)
                self.assertEqual(svc.require_active(),changed)
                svc.confirm('funds',amount=10)
                self.assertEqual(svc.pending['context']['club_id'],2)
                self.assertEqual(svc.pending['context']['budget'],29_000_000)
            finally:selector.shutdown()

    def test_club_change_while_reviewing_funds_returns_to_updated_home(self):
        with tempfile.TemporaryDirectory() as temp:
            selector,profile=self.ready(Path(temp));svc=selector.career_service
            try:
                selector.open(career=True);panel=selector.career_panel
                panel.activate(1);panel.activate(0);panel.digit('9');panel.activate(12)
                self.assertEqual(panel.page,'confirm')
                disk=copy.deepcopy(svc.inspection);profile['club_id']=2
                self.finish_inspection(svc,disk)
                panel.tick();panel.render()
                self.assertEqual(panel.page,'home')
                self.assertIsNone(panel.confirmation)
                self.assertIsNone(svc.pending)
            finally:selector.shutdown()

    def test_unsaved_club_still_allows_new_native_proposal_with_current_source_club(self):
        with tempfile.TemporaryDirectory() as temp:
            selector,profile = self.ready(Path(temp));svc = selector.career_service
            try:
                source=Path(svc.selected['path']);original=source.read_bytes()
                disk=copy.deepcopy(svc.inspection);profile['club_id']=2
                self.finish_inspection(svc,disk)
                selector.open(career=True);panel=selector.career_panel
                panel.page='clubs';panel.country=14;panel.reset_filters();panel.team=1
                panel.activate(3)
                self.assertEqual(panel.page,'confirm')
                panel.activate(0)
                self.assertEqual(svc.pending['action'],'live_job')
                self.assertEqual(svc.pending['context']['club_id'],2)
                self.assertEqual(svc.jobs_runtime.request.call_args.args[0]['club_id'],2)
                self.assertEqual(source.read_bytes(),original)
            finally:selector.shutdown()

    def test_unrelated_user_waits_for_save_without_an_endless_loading_cycle(self):
        with tempfile.TemporaryDirectory() as temp:
            selector,profile=self.ready(Path(temp));svc=selector.career_service
            try:
                disk=copy.deepcopy(svc.inspection);profile['userid']=7
                self.finish_inspection(svc,disk)
                self.assertEqual(svc.state,'waiting_save')
                self.assertIsNone(svc.inspection)
                with patch.object(svc,'_job') as job:
                    for _ in range(30):svc._next_active_check=0;svc.sync_active()
                    job.assert_not_called()
                panel=CareerPanel(selector,svc)
                self.assertEqual(panel.data_gate(),'save')
                profile['userid']=0;svc._next_active_check=0;svc.sync_active()
                self.assertEqual(svc.state,'ready')
                self.assertEqual(svc.inspection['context'],disk['context'])
            finally:selector.shutdown()

    def test_only_current_confirmed_contract_notifies_once(self):
        with tempfile.TemporaryDirectory() as temp:
            selector,profile=self.ready(Path(temp));svc=selector.career_service
            try:
                svc.confirm('transfer',team_id=1,league_id=13)
                svc.feedback.show.reset_mock()
                for _ in range(10):svc._poll_live_request()
                svc.feedback.show.assert_not_called()
                svc.jobs_runtime.poll.return_value={'proposal_received':True,'native_contract_queued':True,
                    'team_id':1,'league_id':13,'valid_for_days':3}
                svc._poll_live_request()
                for _ in range(40):svc._poll_live_request();svc.restore_live_vacancies()
                svc.feedback.show.assert_called_once()
                self.assertEqual(svc.feedback.show.call_args.args[0],'done')
                self.assertIn('confirmada',svc.feedback.show.call_args.args[1])
            finally:selector.shutdown()

    def test_offer_without_native_contract_ack_cannot_show_proposal_received(self):
        with tempfile.TemporaryDirectory() as temp:
            selector,profile=self.ready(Path(temp));svc=selector.career_service
            try:
                svc.confirm('transfer',team_id=1,league_id=13)
                svc.feedback.show.reset_mock()
                svc.jobs_runtime.poll.return_value={'proposal_received':True,'native_contract_queued':False}
                svc._poll_live_request()
                self.assertEqual(svc.state,'error')
                self.assertEqual(svc.feedback.show.call_args.args[0],'error')
                self.assertFalse((svc.root/'last_live_applied.json').exists())
            finally:selector.shutdown()


if __name__=='__main__':unittest.main()
