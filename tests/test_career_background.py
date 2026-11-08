"""Persistent background preference and one-step navigation across input devices."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from server16_py.frontend_stadium_selection import (
    BACKGROUND_MODES,background_mode,save_background_mode,save_enabled,enabled,
)
from server16_py.frontend_stadium_panel import FrontendStadiumPanel

class CareerBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.game=Path(self.temp.name)
        self.config=self.game/'ModCarrerMode/config/frontend_stadium.ini'
        self.config.parent.mkdir(parents=True)
        self.config.write_text('[frontend_stadium]\nenabled=1\nreload_revision=99\n[frontend_stadium_clubs]\n1043=original\n')

    def selector(self,career=True):
        return SimpleNamespace(app=SimpleNamespace(exedir=self.game,log=Mock()),
            _frontend_career=career,render=Mock(),close=Mock(),open=Mock(),open_gamepads=Mock())

    def test_legacy_preference_and_compatibility_switch(self):
        self.assertEqual(background_mode(self.game),'stadium')
        save_enabled(self.game,False)
        self.assertEqual(background_mode(self.game),'image')
        save_enabled(self.game,True)
        self.assertEqual(background_mode(self.game),'stadium')

    def test_persist_each_mode_without_changing_match_assignments_or_reload(self):
        for mode in BACKGROUND_MODES:
            save_background_mode(self.game,mode)
            self.assertEqual(background_mode(self.game),mode)
            self.assertEqual(enabled(self.game),mode!='image')
            text=self.config.read_text()
            self.assertIn('1043 = original',text)
            self.assertIn('reload_revision = 99',text)
        before=self.config.read_bytes()
        with self.assertRaises(ValueError):save_background_mode(self.game,'unknown')
        self.assertEqual(before,self.config.read_bytes())

    def test_direction_and_confirm_change_exactly_one_option(self):
        p=FrontendStadiumPanel(self.selector());p.focus=0
        p.handle(3,0);self.assertEqual(p.mode,'dressing_room')
        p.handle(2,0);self.assertEqual(p.mode,'stadium')
        p.handle(6,0);self.assertEqual(p.mode,'dressing_room')
        p.handle(6,0);self.assertEqual(p.mode,'image')
        self.assertNotIn(1,dict(p.targets()))
        self.assertEqual(FrontendStadiumPanel(self.selector()).mode,'image')

    def test_mouse_arrows_and_back(self):
        s=self.selector();p=FrontendStadiumPanel(s)
        def click(x,y):p.handle(8,int(y*p.SCALE)<<16|int(x*p.SCALE))
        click(540,157);self.assertEqual(p.mode,'dressing_room')
        click(48,157);self.assertEqual(p.mode,'stadium')
        p.handle(7,0);s.close.assert_called_once()

    def test_initial_menu_cycles_only_image_and_stadium(self):
        p=FrontendStadiumPanel(self.selector(False))
        for _ in range(6):
            p.shift_background()
            self.assertNotEqual(p.mode,'dressing_room')

if __name__=='__main__':unittest.main()
