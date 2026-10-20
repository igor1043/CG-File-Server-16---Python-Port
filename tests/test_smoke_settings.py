import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server16_py.match_presentation import MatchPresentation,PresentationOptions
from server16_py.smoke_settings_panel import SmokeSettingsPanel
import test_prematch_panel as fixtures


class SmokeSettingsTests(unittest.TestCase):
    def open_panel(self,root):
        selector=fixtures.PrematchTests().selector(root)
        selector.open(hub=True);selector.handle(16,3)
        parent=selector.prematch_panel;parent.activate(6)
        return selector,parent,parent.child

    def test_settings_roundtrip_legacy_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=MatchPresentation(tmp);store.path.parent.mkdir(parents=True)
            store.path.write_text('[match]\nmascots=0\npyrotechnics=1\nentrance=1\ngoal=0\n')
            options=store.load();self.assertEqual(options.smoke_entrance_seconds,60)
            self.assertEqual(options.smoke_goal_emitters,4095)
            options.smoke_entrance_seconds=120;options.smoke_goal_seconds=15
            options.smoke_entrance_emitters=1<<18;options.smoke_goal_emitters=0
            store.save(options);self.assertEqual(store.load(),options)
            old=store.path.read_bytes()
            for key,value in [('smoke_goal_seconds',14),('smoke_goal_seconds',121),('smoke_entrance_emitters',1<<20),('smoke_goal_emitters',-1)]:
                invalid=PresentationOptions();setattr(invalid,key,value)
                with self.assertRaises(ValueError):store.save(invalid)
                self.assertEqual(store.path.read_bytes(),old)

    def test_draft_cancel_and_parent_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector,parent,panel=self.open_panel(Path(tmp))
            try:
                panel.activate(7);panel.activate(8+18);panel.activate(2)
                self.assertEqual(parent.options.smoke_entrance_emitters,1<<18)
                self.assertEqual(parent.options.smoke_entrance_seconds,55)
                panel.handle(7,0);self.assertIsNone(parent.child);self.assertEqual(parent.HEIGHT,545)
                selector.handle(16,2) # Cancel the entire draft.
                self.assertFalse(parent.store.path.exists())
                selector.handle(16,3);parent=selector.prematch_panel;parent.activate(6);panel=parent.child
                panel.activate(1);panel.activate(7);panel.activate(8+9);panel.activate(3)
                self.assertEqual(parent.options.smoke_goal_emitters,2)
                panel.handle(7,0);selector.handle(16,1)
                saved=parent.store.load();self.assertEqual(saved.smoke_goal_seconds,30)
                self.assertEqual(saved.smoke_goal_emitters,2)
            finally:selector.shutdown()

    def test_maps_match_native_sites_and_goal_mask_shift(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector,parent,panel=self.open_panel(Path(tmp))
            try:
                self.assertEqual(len(panel.positions()),20)
                panel.activate(5);self.assertEqual(panel.mask(),255)
                panel.activate(6);self.assertEqual(panel.mask(),0xfff00)
                panel.activate(1);panel.activate(5);self.assertEqual(panel.mask(),0x555)
                panel.activate(6);self.assertEqual(panel.mask(),0xaaa)
                old=panel.mask();panel.activate(8);self.assertEqual(panel.mask(),old)
                self.assertNotIn(8,dict(panel.targets()))
                self.assertIn(27,dict(panel.targets()))
            finally:selector.shutdown()

    def test_controller_mouse_render_and_duration_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector,parent,panel=self.open_panel(Path(tmp))
            try:
                for _ in range(30):panel.activate(2)
                self.assertEqual(parent.options.smoke_entrance_seconds,15)
                for _ in range(30):panel.activate(3)
                self.assertEqual(parent.options.smoke_entrance_seconds,120)
                panel.focus=0;panel.handle(3,0);self.assertEqual(panel.focus,1)
                panel.handle(6,0);self.assertTrue(panel.goal)
                x,y=panel.positions()[19];old=panel.mask()
                panel.handle(8,(y<<16)|x);self.assertEqual(panel.mask(),old^(1<<11))
                self.assertEqual(panel.render().size,(1200,1240))
                self.assertEqual(parent.render().size,(1200,1240))
                panel.handle(11,0);self.assertFalse(selector.opened)
                self.assertFalse(parent.store.path.exists())
            finally:selector.shutdown()

    def test_save_failure_preserves_old_mask_and_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=MatchPresentation(tmp);store.save(PresentationOptions());old=store.path.read_bytes()
            changed=store.load();changed.smoke_entrance_emitters=0;changed.smoke_goal_seconds=50
            with patch('server16_py.match_presentation.os.replace',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):store.save(changed)
            self.assertEqual(store.path.read_bytes(),old)
