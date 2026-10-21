"""Unfinished features stay hidden without deleting their implementation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import server16_py as features
from server16_py.prematch_panel import PrematchPanel
from server16_py.match_hub_panel import MatchHubPanel
from server16_py.app import Server16App
import test_match_audio_panel as fixtures


class ReleaseFeaturesTests(unittest.TestCase):
    def test_narration_loading_and_applied_notifications_are_hidden(self):
        app=SimpleNamespace(log=Mock(),show_narration_loading=Mock(),
                            _hide_asset_loading=Mock(),_show_asset_loading=Mock(),
                            _ensure_d3d_overlay_injected=Mock())
        Server16App.show_narration_applied(app,'Narrador')
        Server16App.show_narration_loading(app,'Narrador')
        Server16App._show_asset_loading(app,'narration','Narração aplicada','Narrador','',100)
        app.show_narration_loading.assert_not_called()
        app._hide_asset_loading.assert_not_called()
        app._show_asset_loading.assert_not_called()
        app._ensure_d3d_overlay_injected.assert_not_called()
        with patch.object(features,'NARRATION_PICKER_AVAILABLE',True):
            Server16App.show_narration_applied(app,'Narrador')
        app.show_narration_loading.assert_called_once_with('Narrador',100,'Narração aplicada')

    def test_public_prematch_has_no_hidden_shortcuts_or_empty_cards(self):
        self.assertFalse(features.EXTRA_SCENES_AVAILABLE)
        self.assertFalse(features.NARRATION_PICKER_AVAILABLE)
        with tempfile.TemporaryDirectory() as folder:
            selector=fixtures.MatchAudioTests().make_selector(Path(folder))
            try:
                selector.open(hub=True)
                panel=selector.prematch_panel
                self.assertIsInstance(panel,PrematchPanel)
                self.assertEqual([action for action,_,_ in panel.cards()],[0,1,2])
                self.assertEqual(panel.cards()[-1][1][2],576)
                for key in (4,5):panel.handle(16,key)
                for action in (3,4):panel.activate(action)
                self.assertIs(selector.prematch_panel,panel)
                for connected in (False,True):
                    selector.controller_connected=connected
                    self.assertEqual(panel.render().size,(1200,panel.HEIGHT*2))
            finally:selector.shutdown()

    def test_public_match_menu_closes_instead_of_opening_extra_scenes(self):
        with tempfile.TemporaryDirectory() as folder:
            selector=fixtures.MatchAudioTests().make_selector(Path(folder))
            try:
                selector.open(audio=True)
                panel=selector.audio_panel
                self.assertIsInstance(panel,MatchHubPanel)
                self.assertEqual([label for label,_ in panel.items()],['Música','Gráficos','Câmera','Fechar'])
                panel.handle(16,4)
                self.assertFalse(selector.opened)
                self.assertIsNone(panel.child)
            finally:selector.shutdown()

    def test_development_gates_restore_both_preserved_panels(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(features,'NARRATION_PICKER_AVAILABLE',True), \
             patch.object(features,'EXTRA_SCENES_AVAILABLE',True):
            selector=fixtures.MatchAudioTests().make_selector(Path(folder))
            try:
                panel=PrematchPanel(selector)
                self.assertEqual([action for action,_,_ in panel.cards()],[0,1,2,3,4])
                self.assertIn('Cenas extras',[label for label,_ in MatchHubPanel(selector).items()])
                with patch.object(selector,'render'),patch('server16_py.prematch_panel.NarrationPanel') as narration:
                    panel.activate(3)
                    narration.assert_called_once_with(selector)
            finally:selector.shutdown()

    def test_hidden_narration_does_not_select_or_connect_automatically(self):
        with tempfile.TemporaryDirectory() as folder:
            selector=fixtures.MatchAudioTests().make_selector(Path(folder))
            try:
                app=selector.app
                app._narration_runtime=Mock()
                with patch('server16_py.stadium_selector.narration_runtime') as narration:
                    selector.tick()
                    narration.assert_not_called()
                app._narration_runtime.tick.assert_not_called()
            finally:selector.shutdown()


if __name__=='__main__':unittest.main()
