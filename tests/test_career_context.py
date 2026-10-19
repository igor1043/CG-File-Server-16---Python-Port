import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.career_context import CareerContext, _career_service_active
import test_career_overlay as fixtures

HUB='game/screens/fluxHub/FluxHub'


class CareerContextTests(unittest.TestCase):
    def reader(self):
        memory=SimpleNamespace(process_id=123,get_int=Mock(return_value=0))
        app=SimpleNamespace(memory=memory,offsets=SimpleNamespace(GAMESTARTEDBINARYBASE=1,GAMESTARTEDBINARY=[2]))
        return CareerContext(app)

    def test_shared_hub_requires_native_career_and_no_match(self):
        reader=self.reader()
        with patch('server16_py.career_context.competition_session',return_value=True):
            self.assertTrue(reader.career_hub(HUB))
            reader.app.memory.get_int.return_value=1
            self.assertFalse(reader.career_hub(HUB))
        for session in (False,None):
            reader=self.reader()
            with patch('server16_py.career_context.competition_session',return_value=session):
                self.assertFalse(reader.career_hub(HUB))

    def test_tournament_hub_and_unknown_reads_are_not_career(self):
        reader=self.reader()
        with patch('server16_py.career_context.competition_session',return_value=True):
            reader.observe('game/screens/tournament/TournamentHub')
            self.assertFalse(reader.career_hub(HUB))
            reader.observe('game/screens/career/Calendar')
            self.assertTrue(reader.career_hub(HUB))
            reader.app.memory.get_int.side_effect=RuntimeError('unreadable')
            self.assertFalse(reader.career_hub(HUB))

    def test_ambiguous_hub_never_authorizes_publication(self):
        for session in (True,None):
            reader=self.reader()
            with patch('server16_py.career_context.competition_session',return_value=session):
                self.assertFalse(reader.exited_hub(HUB,fresh=True))
        reader=self.reader()
        with patch('server16_py.career_context.competition_session',return_value=False):
            self.assertTrue(reader.exited_hub(HUB,fresh=True))
            reader.app.memory.get_int.return_value=1
            self.assertFalse(reader.exited_hub(HUB,fresh=True))

    def test_native_accessor_layout_changes_are_rejected(self):
        memory=SimpleNamespace(base_module=0x140000000,read_process_memory=Mock(return_value=b'unsupported'))
        self.assertIsNone(_career_service_active(memory,[(0x70000000,0x100000)]))

    def test_actual_flux_page_routes_career_without_stealing_match_pause(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=fixtures.CareerOverlayTests().make_ready(Path(temporary))
            try:
                selector.app.lastpagename=HUB
                reader=selector.career_service.context_reader
                reader.started=Mock(return_value=0)
                reader.session=Mock(return_value=True)
                selector.shared.ready=7;selector._attempted_pid=1234
                selector.shared.events[0].kind=1;selector.shared.write_index=1
                selector.tick()
                self.assertEqual(selector.shared.enabled,3)
                self.assertIsNotNone(selector.career_panel)
                selector.close()
                # The same FluxHub while a fixture is active belongs to the
                # existing match menu, even with the career service loaded.
                reader.started.return_value=1
                selector.app._is_game_running_with=Mock(return_value=True)
                selector.tick()
                self.assertEqual(selector.shared.enabled,2)
                self.assertIsNone(selector.career_panel)
                reader.started.return_value=0;reader.session.return_value=None
                selector.app._is_game_running_with.return_value=False
                selector._match_context=None
                selector.tick()
                self.assertEqual(selector.shared.enabled,0)
            finally:selector.shutdown()

    def test_confirming_from_real_career_hub_uses_same_save_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            selector=fixtures.CareerOverlayTests().make_ready(Path(temporary))
            try:
                selector.app.lastpagename=HUB
                reader=selector.career_service.context_reader
                reader.started=Mock(return_value=0);reader.session=Mock(return_value=True)
                selector.career_service.confirm('funds',amount=100)
                self.assertEqual(selector.career_service.state,'waiting_exit')
                self.assertFalse(selector.career_service.safe_to_apply(fresh=True))
            finally:selector.shutdown()


if __name__=='__main__':unittest.main()
