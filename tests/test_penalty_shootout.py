from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

from server16_py.app import Server16App
from server16_py.file_tools import restore_native_assets
from server16_py.match_state import outside_match_page, penalty_shootout_page, post_match_page


class PenaltyShootoutTests(unittest.TestCase):
    def test_penalty_taker_selection_is_a_live_fixture_overlay(self):
        for page in ('game/screens/postGameFlow/PenaltyKickSelect',
                     'GAME/SCREENS/POSTGAMEFLOW/PENALTYKICKSELECT'):
            self.assertTrue(penalty_shootout_page(page))
            self.assertFalse(post_match_page(page))
            self.assertFalse(outside_match_page(page))
        for page in ('game/screens/postGameFlow/MatchResults',
                     'game/screens/postGameFlow/MatchHighlights', 'MatchForfeit'):
            self.assertFalse(penalty_shootout_page(page))
            self.assertTrue(post_match_page(page))

    def test_scoreboard_files_survive_selection_kicks_pause_and_end_only_at_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            native=root/'FSW/ScoreBoard/score.big';native.parent.mkdir(parents=True)
            native.write_bytes(b'original scoreboard')
            active=root/'data/ui/game/score.big';active.parent.mkdir(parents=True)
            active.write_bytes(b'assigned competition scoreboard with shootout assets')
            app=SimpleNamespace(exedir=root, lastpagename='', HID='1043', AID='1035', matchstarted=True,
                _match_audio_ended=False, _native_assets_restored_for_match=False,
                _last_runtime_signature=('1043','1035'), skillgamechange=False,
                _is_post_match_page=Server16App._is_post_match_page,
                _reset_chants_state=Mock(), _reset_team_entrance=Mock(), log=Mock())
            app._restore_native_runtime_assets=lambda:restore_native_assets(app)
            expected=active.read_bytes()
            for page in ('game/screens/postGameFlow/PenaltyKickSelect', '',
                         'game/screens/fluxHub/FluxHub', '',
                         'game/screens/instantReplay/ReplayScreen', ''):
                Server16App._handle_page_transition(app,page)
                self.assertEqual(active.read_bytes(),expected)
                self.assertFalse(app._native_assets_restored_for_match)
                self.assertFalse(app._match_audio_ended)
            app._reset_chants_state.assert_not_called()
            Server16App._handle_page_transition(app,'game/screens/postGameFlow/MatchResults')
            self.assertEqual(active.read_bytes(),native.read_bytes())
            self.assertTrue(app._native_assets_restored_for_match)
            self.assertTrue(app._match_audio_ended)


if __name__=='__main__':unittest.main()
