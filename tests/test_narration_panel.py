import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import test_stadium_selector as fixtures

class NarrationPanelTests(unittest.TestCase):
    def setUp(self):
        # This preserved developer UI is intentionally hidden in public builds.
        gate=patch('server16_py.NARRATION_PICKER_AVAILABLE',True)
        gate.start();self.addCleanup(gate.stop)

    def test_narrator_selection_applies_and_returns_to_prematch_menu(self):
        options=[dict(name=n,commentator='Caio Ribeiro') for n in ('Tiago Leifert','Vilani','Luiz Roberto')]
        runtime=SimpleNamespace(current='Tiago Leifert',pending=None,error='',profiles=lambda:options,apply=Mock())
        with tempfile.TemporaryDirectory() as tmp,patch('server16_py.narration_panel.narration_runtime',return_value=runtime):
            selector=fixtures.StadiumSelectorTests().make_selector(Path(tmp))
            selector.app.show_narration_applied=Mock()
            try:
                selector.open(hub=True);selector.handle(16,4)
                panel=selector.prematch_panel
                selector.handle(5,0);selector.handle(6,0)
                self.assertEqual(panel.index,1)
                selector.handle(16,1);runtime.apply.assert_called_once_with('Vilani')
                runtime.pending='Vilani';panel.tick()
                self.assertTrue(selector.opened);selector.app.show_narration_applied.assert_not_called()
                runtime.pending=None;runtime.current='Vilani';panel.tick()
                self.assertTrue(selector.opened)
                self.assertTrue(selector.prematch_panel is not None)
                self.assertFalse(selector.prematch_panel.crowd)
                selector.app.show_narration_applied.assert_not_called() # Runtime owns notifications.
            finally:selector.shutdown()
    def test_empty_catalog_navigation_is_valid(self):
        runtime=SimpleNamespace(current='Tiago Leifert',pending=None,error='',profiles=lambda:[],apply=Mock())
        with tempfile.TemporaryDirectory() as tmp,patch('server16_py.narration_panel.narration_runtime',return_value=runtime):
            selector=fixtures.StadiumSelectorTests().make_selector(Path(tmp))
            try:
                selector.open(hub=True);selector.handle(16,4);selector.handle(3,0)
                self.assertEqual(selector.prematch_panel.focus,4)
            finally:selector.shutdown()
    def test_failed_application_keeps_selector_open(self):
        runtime=SimpleNamespace(current='Tiago Leifert',pending=None,error='Perfil rejeitado',profiles=lambda:[dict(name='Vilani',commentator='Caio')],apply=Mock())
        with tempfile.TemporaryDirectory() as tmp,patch('server16_py.narration_panel.narration_runtime',return_value=runtime):
            selector=fixtures.StadiumSelectorTests().make_selector(Path(tmp));selector.app.show_narration_applied=Mock()
            try:
                selector.open(hub=True);selector.handle(16,4);selector.handle(16,1)
                selector.prematch_panel.tick()
                self.assertTrue(selector.opened)
                self.assertEqual(selector.prematch_panel.message,'Perfil rejeitado')
                selector.app.show_narration_applied.assert_not_called()
            finally:selector.shutdown()
    def test_additional_narrator_can_be_reached_with_controller(self):
        options=[dict(name=n,commentator='') for n in ('Tiago Leifert','Vilani','Luiz Roberto','Novo narrador')]
        runtime=SimpleNamespace(current='Tiago Leifert',pending=None,error='',profiles=lambda:options,apply=Mock())
        with tempfile.TemporaryDirectory() as tmp,patch('server16_py.narration_panel.narration_runtime',return_value=runtime):
            selector=fixtures.StadiumSelectorTests().make_selector(Path(tmp))
            try:
                selector.open(hub=True);selector.handle(16,4)
                for _ in range(3):selector.handle(5,0)
                selector.handle(6,0);selector.handle(16,1)
                runtime.apply.assert_called_once_with('Novo narrador')
            finally:selector.shutdown()
