import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_prematch_panel as pre
import test_match_audio_panel as audio
from server16_py.cloth_motion_switch import ClothMotionSwitch


def install(root):
    switch=ClothMotionSwitch(root);switch.ini_path.parent.mkdir(parents=True,exist_ok=True)
    switch.dll_path.write_bytes(b'fixture');switch.ini_path.write_bytes(b'[cloth_motion]\nenabled=1\nsolver_hz=120\n')
    switch.list_path.write_bytes(b'other\\module.dll\ncloth_motion\\cloth_motion.dll\n');return switch


class LiveClothTests(unittest.TestCase):
    def test_status_rejects_stale_foreign_and_malformed(self):
        with tempfile.TemporaryDirectory() as tmp:
            switch=install(Path(tmp))
            for data,expected in [('CM1 42 1000 1',True),('CM1 42 1000 0',False),('bad',None),('CM1 42 1000 9',None),('CM1 41 1000 1',None)]:
                switch.state_path.write_text(data);self.assertIs(switch.live_enabled(pid=42,now=1200),expected)
            switch.state_path.write_text('CM1 42 1000 1')
            self.assertIsNone(switch.live_enabled(pid=42,now=5000));self.assertIsNone(switch.live_enabled(pid=42,now=900))

    def test_pre_match_cancel_apply_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);selector=pre.PrematchTests().selector(root)
            switch=install(getattr(selector.app,'exedir',selector.app.base_dir))
            try:
                selector.open(hub=True);selector.handle(16,3);panel=selector.prematch_panel
                panel.activate(5);self.assertFalse(panel.cloth_enabled);selector.handle(16,2)
                self.assertTrue(switch.enabled())
                selector.handle(16,3);panel=selector.prematch_panel;panel.activate(5);selector.handle(16,1)
                self.assertFalse(switch.enabled());self.assertIn(b'cloth_motion',switch.list_path.read_bytes())
                selector.handle(16,3);panel=selector.prematch_panel;panel.activate(5)
                original=panel.store.path.read_bytes()
                with patch.object(panel.cloth,'set_enabled',side_effect=OSError('disk full')):
                    panel.activate(len(panel.ROWS)+1)
                self.assertEqual(original,panel.store.path.read_bytes());self.assertFalse(switch.enabled())
                self.assertIn('possível',panel.message)
            finally:selector.shutdown()

    def test_in_match_mouse_keyboard_ack_and_audio_independence(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=audio.MatchAudioTests().make_selector(Path(tmp));switch=install(selector.app.exedir)
            try:
                selector.open(audio=True);panel=selector.audio_panel
                panel.activate(1)  # Graphics category.
                before=(selector.app._crowd_master_volume,selector.app._goal_master_volume)
                panel.handle(6,0)
                self.assertFalse(switch.enabled())
                self.assertEqual((selector.app._crowd_master_volume,selector.app._goal_master_volume),before)
                with patch.object(panel.cloth,'live_enabled',return_value=False):panel.tick()
                self.assertFalse(panel.cloth_pending);self.assertIn('aplicada',panel.message)
                panel.handle(6,0);self.assertTrue(switch.enabled())
                panel._next_tick=0
                with patch.object(panel.cloth,'live_enabled',return_value=True):panel.tick()
                self.assertFalse(panel.cloth_pending)
                selector.handle(11,0);self.assertTrue(switch.enabled())
            finally:selector.shutdown()

    def test_live_draft_rejects_expired_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=audio.MatchAudioTests().make_selector(Path(tmp));switch=install(selector.app.exedir)
            try:
                selector.open(audio=True);selector.audio_panel.activate(1);selector.app.HID='changed';selector.audio_panel.activate(0)
                self.assertFalse(selector.opened);self.assertTrue(switch.enabled())
            finally:selector.shutdown()

if __name__=='__main__':unittest.main()
