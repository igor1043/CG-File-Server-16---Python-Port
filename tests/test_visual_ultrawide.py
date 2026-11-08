from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from server16_py.app import Server16App
from server16_py.locales_data import LOCALE_CATALOGS
from server16_py.frontend_stadium_panel import FrontendStadiumPanel
from server16_py.match_settings_panel import MatchSettingsPanel
from server16_py.native_feature_switch import UltrawideSwitch
from server16_py.ultrawide_background import NATIVE,VARIANTS,STANDARD,WIDE
from test_career_overlay import CareerOverlayTests
from test_ultrawide_background import dds

class VisualUltrawideTests(unittest.TestCase):
    def setUp(self):
        sound = patch('server16_py.career_feedback.play_sound')
        sound.start()
        self.addCleanup(sound.stop)

    def prepare(self,root):
        selector=CareerOverlayTests().make_ready(root)
        game=selector.app.exedir;switch=UltrawideSwitch(game)
        switch.ini.parent.mkdir(parents=True);switch.ini.write_bytes(b'[ultrawide]\nenabled=0\n')
        dll=switch.mods/switch.module;dll.parent.mkdir();dll.touch()
        folder=game/VARIANTS;folder.mkdir(parents=True)
        (folder/STANDARD).write_bytes(dds(128,72,19));(folder/WIDE).write_bytes(dds(192,72,27))
        return selector,switch

    def test_menu_and_career_switch_does_not_depend_on_custom_stadium(self):
        for career in (False,True):
            for stadium in (False,True):
                with self.subTest(career=career,stadium=stadium),tempfile.TemporaryDirectory() as tmp:
                    selector,switch=self.prepare(Path(tmp))
                    try:
                        selector._frontend_career=career;panel=FrontendStadiumPanel(selector);panel.enabled=stadium
                        self.assertIn(5,dict(panel.targets()))
                        panel.focus=5;panel.handle(6,0)  # Controller confirm/A.
                        self.assertTrue(switch.enabled());self.assertIn('Reinicie o FIFA',panel.message)
                        self.assertEqual((selector.app.exedir/NATIVE).read_bytes(),(selector.app.exedir/VARIANTS/WIDE).read_bytes())
                        panel.handle(3,0)  # D-pad right also toggles immediately.
                        self.assertFalse(switch.enabled())
                        panel.handle(16,4)  # F4.
                        self.assertTrue(switch.enabled())
                        r=dict(panel.targets())[5]
                        x=int((r[0]+r[2])/2*panel.SCALE);y=int((r[1]+r[3])/2*panel.SCALE)
                        panel.handle(8,(y<<16)|x)
                        self.assertFalse(switch.enabled())
                    finally:selector.shutdown()

    def test_prematch_switch_applies_without_pressing_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector,switch=self.prepare(Path(tmp))
            try:
                panel=MatchSettingsPanel(selector);panel.focus=7;panel.handle(6,0)
                self.assertTrue(switch.enabled());self.assertIn('Reinicie o FIFA',panel.message)
                self.assertEqual((selector.app.exedir/NATIVE).read_bytes(),(selector.app.exedir/VARIANTS/WIDE).read_bytes())
                panel.handle(6,0);self.assertFalse(switch.enabled())
            finally:selector.shutdown()

    def test_failed_visual_toggle_keeps_current_state_and_shows_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector,switch=self.prepare(Path(tmp))
            try:
                selector._frontend_career=True;panel=FrontendStadiumPanel(selector)
                (selector.app.exedir/VARIANTS/WIDE).write_bytes(b'DDS incomplete')
                panel.activate(5)
                self.assertFalse(switch.enabled());self.assertIn('Não foi possível',panel.message)
                self.assertFalse(hasattr(selector.app, '_ultrawide_feedback'))
            finally:selector.shutdown()

    def test_desktop_switch_notifies_only_after_a_successful_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector, switch = self.prepare(Path(tmp))
            feedback = Mock()
            app = SimpleNamespace(
                exedir=selector.app.exedir, module_states={},
                tr=LOCALE_CATALOGS['pt'].__getitem__, _ultrawide_feedback=feedback,
            )
            var = Mock()
            var.get.return_value = True
            try:
                Server16App._on_module_toggle(app, 'Ultrawide', var)
                self.assertTrue(switch.enabled())
                self.assertIn('Reinicie o FIFA', feedback.show.call_args.args[1])
                Server16App._on_module_toggle(app, 'Ultrawide', var)
                feedback.show.assert_called_once()
                var.get.return_value = False
                (app.exedir / VARIANTS / STANDARD).write_bytes(b'DDS incomplete')
                with patch('server16_py.app.messagebox.showerror') as error:
                    Server16App._on_module_toggle(app, 'Ultrawide', var)
                    error.assert_called_once()
                self.assertTrue(switch.enabled())
                var.set.assert_called_once_with(True)
                feedback.show.assert_called_once()
            finally:
                selector.shutdown()

if __name__=='__main__':unittest.main()
