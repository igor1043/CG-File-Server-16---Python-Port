import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import test_career_overlay as fixtures
from server16_py.career_feedback import CareerFeedback
from server16_py.career_save_worker import fingerprint


class StickyFeedbackTests(unittest.TestCase):
    def feedback(self):
        app=SimpleNamespace(memory=SimpleNamespace(process_id=123,is_open=Mock(return_value=True)),
                            log=Mock(),after=Mock(return_value='timer'),after_cancel=Mock())
        return CareerFeedback(app)

    def test_native_progress_is_replaced_by_temporary_success(self):
        feedback=self.feedback()
        with patch('server16_py.career_feedback.native_notice',return_value=True) as notice, \
             patch('server16_py.career_feedback.play_sound'):
            feedback.show('prepared','Saia da carreira','a',persistent=True)
            feedback.show('applying','Aplicando...','a',persistent=True)
            feedback.show('applying','Aplicando...','a',persistent=True)
            self.assertEqual(feedback._progress,('a','Aplicando...'))
            feedback.show('done','Aplicado','a')
            self.assertEqual([c.kwargs['persistent'] for c in notice.call_args_list],[True,True,False])
            self.assertIsNone(feedback._progress)

    def test_fallback_progress_cancels_old_timer_and_completion_gets_five_seconds(self):
        feedback=self.feedback();feedback.window=Mock();feedback.hide_job='old'
        feedback._schedule_hide(True)
        feedback.app.after_cancel.assert_called_once_with('old')
        feedback.app.after.assert_not_called()
        self.assertIsNone(feedback.hide_job)
        feedback._schedule_hide(False)
        feedback.app.after.assert_called_once_with(5000,feedback.window.withdraw)

    def test_progress_survives_game_closure_and_cleans_up_on_server_shutdown(self):
        feedback=self.feedback()
        with patch('server16_py.career_feedback.native_notice',return_value=True) as notice, \
             patch('server16_py.career_feedback.play_sound'),patch.object(feedback,'_fallback') as fallback:
            feedback.show('applying','Aplicando...','a',persistent=True)
            feedback.app.memory.is_open.return_value=False
            feedback.tick();feedback.tick()
            fallback.assert_called_once_with('Aplicando...',persistent=True)
            feedback.close()
            self.assertIsNone(feedback._progress)
            self.assertEqual(notice.call_args.kwargs,{'dismiss':True})


class CareerProgressLifecycleTests(unittest.TestCase):
    def test_progress_remains_until_verified_publication_for_funds_and_both_retirement_rules(self):
        for action in ('funds','remove_retirement','remove_and_rejuvenate'):
            with self.subTest(action=action),tempfile.TemporaryDirectory() as temp:
                selector=fixtures.CareerOverlayTests().make_ready(Path(temp));svc=selector.career_service
                try:
                    svc.confirm(action,**({'amount':10} if action=='funds' else {}))
                    self.assertTrue(svc.feedback.show.call_args.kwargs['persistent'])
                    request=dict(svc.pending);source=Path(request['path']);before=source.read_bytes()
                    svc.notify('applying','Aplicando...')
                    self.assertTrue(svc.feedback.show.call_args.kwargs['persistent'])
                    payload=fixtures.container(1);(svc.root/'prepared_DATA').write_bytes(payload)
                    result={'context':dict(request['context']),'output_sha256':fingerprint(payload)}
                    if action=='funds':result['context']['budget']+=10
                    else:result['retirement']={'players_changed':3,'target_age':18}
                    svc.safe_to_apply=Mock(return_value=False)
                    selector.app.lastpagename='game/screens/mainMenu/MainMenu'
                    svc.events.put(('prepare',request['request_id'],result,None));svc.tick()
                    self.assertEqual(source.read_bytes(),before)
                    self.assertEqual(svc.feedback.show.call_args.args[0],'waiting_exit')
                    self.assertTrue(svc.feedback.show.call_args.kwargs['persistent'])
                    self.assertFalse(any(c.args[0]=='done' for c in svc.feedback.show.call_args_list))
                    svc.safe_to_apply.return_value=True;svc._safe_since=time.monotonic()-3
                    svc.tick();svc.tick()
                    self.assertEqual(source.read_bytes(),payload)
                    self.assertEqual(svc.state,'done')
                    self.assertEqual(svc.feedback.show.call_args.args[0],'done')
                    self.assertFalse(svc.feedback.show.call_args.kwargs['persistent'])
                finally:selector.shutdown()

    def test_failure_and_cancellation_replace_persistent_progress(self):
        for outcome in ('error','cancelled'):
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory() as temp:
                selector=fixtures.CareerOverlayTests().make_ready(Path(temp));svc=selector.career_service
                try:
                    svc.confirm('funds',amount=10)
                    source=Path(svc.pending['path']);before=source.read_bytes()
                    if outcome=='cancelled':svc.cancel()
                    else:svc.events.put(('prepare',None,None,'falha de teste'));svc.tick()
                    self.assertEqual(svc.feedback.show.call_args.args[0],outcome)
                    self.assertFalse(svc.feedback.show.call_args.kwargs['persistent'])
                    self.assertEqual(source.read_bytes(),before)
                finally:selector.shutdown()

    def test_native_proposals_keep_the_normal_temporary_notice(self):
        with tempfile.TemporaryDirectory() as temp:
            selector=fixtures.CareerOverlayTests().make_ready(Path(temp));svc=selector.career_service
            try:
                svc.confirm('transfer',team_id=1,league_id=13)
                self.assertFalse(svc.feedback.show.call_args.kwargs['persistent'])
            finally:selector.shutdown()
