import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from server16_py.crowd_control import CrowdShared
import test_stadium_selector as fixtures
import test_match_audio_panel as audio_fixtures


class PrematchTests(unittest.TestCase):
    def selector(self, root):
        selector=fixtures.StadiumSelectorTests().make_selector(root)
        selector.crowd_control.tick(True,False)
        return selector

    def test_protocol_and_menu_keyboard_controller_mouse(self):
        self.assertEqual(ctypes.sizeof(CrowdShared),52)
        with tempfile.TemporaryDirectory() as tmp:
            selector=self.selector(Path(tmp))
            try:
                selector.open(hub=True)
                self.assertTrue(selector.prematch_panel)
                selector.handle(16,1)
                self.assertTrue(selector.prematch_panel.crowd)
                selector.handle(7,0)
                self.assertFalse(selector.prematch_panel.crowd)
                selector.handle(3,0); selector.handle(6,0)
                self.assertIsNone(selector.prematch_panel)
                self.assertTrue(selector.return_to_menu)
                selector.handle(7,0)
                self.assertTrue(selector.prematch_panel)
                selector.handle(8,(150<<16)|150)
                self.assertTrue(selector.prematch_panel.crowd)
                selector.handle(11,0)
                self.assertFalse(selector.opened)
            finally: selector.shutdown()

    def test_cancel_does_not_write_and_native_confirmation_returns_to_menu(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=self.selector(Path(tmp))
            try:
                shared=selector.crowd_control.shared
                shared.status=2; shared.current_percent=65; shared.automatic_percent=65
                shared.ack=shared.command
                selector.open(hub=True); selector.handle(16,1)
                self.assertEqual(selector.prematch_panel.value,65)
                selector.handle(2,0); selector.handle(7,0)
                self.assertEqual(shared.requested_percent,-1)
                selector.handle(16,1); selector.handle(12,(167<<16)|40)
                self.assertEqual(selector.prematch_panel.value,0)
                selector.handle(16,1)
                self.assertEqual(shared.requested_percent,0)
                command=selector.prematch_panel.command
                self.assertIsNotNone(command)
                shared.ack=command; shared.status=3; shared.current_percent=0
                selector.prematch_panel.tick()
                self.assertFalse(selector.prematch_panel.crowd)
                self.assertEqual(shared.automatic_percent,65)
                selector.handle(16,1)
                self.assertEqual(selector.prematch_panel.value,0)
            finally:
                del shared
                selector.shutdown()

    def test_no_bridge_rejects_apply_and_timeout_clears_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=self.selector(Path(tmp))
            try:
                selector.open(hub=True); selector.handle(16,1); selector.handle(16,1)
                self.assertEqual(selector.crowd_control.shared.requested_percent,-1)
                shared=selector.crowd_control.shared; shared.status=2; shared.current_percent=56
                shared.ack=shared.command
                selector.prematch_panel.tick(); selector.handle(16,1)
                selector.prematch_panel.deadline=0; selector.prematch_panel.tick()
                self.assertEqual(shared.requested_percent,-1)
                self.assertIsNone(selector.prematch_panel.command)
            finally:
                del shared
                selector.shutdown()

    def test_per_fixture_override_survives_loading_and_clears_next_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=self.selector(Path(tmp))
            try:
                control=selector.crowd_control; control.shared.status=2
                control.shared.ack=control.shared.command
                control.apply(56,selector._context())
                self.assertTrue(selector.keep_crowd_on_setup_return('game/screens/StadiumPan'))
                selector.app.lastpagename=''
                selector.tick()
                self.assertEqual(control.shared.requested_percent,56)
                selector.app.lastpagename='game/screens/TV/bumper'
                selector.tick()
                self.assertEqual(control.shared.requested_percent,56)
                self.assertEqual(control.shared.phase,2)
                selector.app._kickoff_generation+=1
                control.tick(True,False)
                self.assertEqual(control.shared.requested_percent,-1)
                self.assertEqual(control.shared.current_percent,-1)
                with self.assertRaises(RuntimeError):
                    control.apply(100,selector._context())
                control.shared.status=2; control.shared.ack=control.shared.command
                control.apply(100,selector._context())
                selector.app._match_audio_ended=True
                control.tick(False,False)
                self.assertEqual(control.shared.requested_percent,-1)
            finally: selector.shutdown()

    def test_career_menu_releases_manual_even_when_next_fixture_has_same_teams(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=self.selector(Path(tmp))
            try:
                control=selector.crowd_control
                control.shared.status=2
                control.shared.ack=control.shared.command
                control.apply(56,selector._context())
                selector.app.lastpagename='game/screens/career/CareerHub'
                selector.tick()
                self.assertEqual(control.shared.requested_percent,-1)
                self.assertEqual(control.shared.phase,0)
                # Career does not always use the friendly kickoff generation.
                # Even the same teams must not recover the previous request.
                selector.app.lastpagename='game/screens/career/PreMatchHub'
                selector.tick()
                self.assertEqual(control.shared.phase,1)
                self.assertEqual(control.shared.requested_percent,-1)
            finally:
                selector.shutdown()

    def test_stadium_apply_returns_to_menu_and_keyboard_search_does_not_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'BRA - Test.zip').touch()
            selector=self.selector(root)
            try:
                selector.open(hub=True); selector.handle(16,2)
                selector._catalog_thread.join(5); selector._drain_catalog()
                selector.handle(9,0); selector.handle(10,ord('M'))
                selector.handle(16,1)
                selector.app.stadium_runtime.apply_manual_stadium.assert_not_called()
                selector.query=selector.draft=''; selector.refresh()
                selector.handle(16,1)
                selector.app.stadium_runtime.apply_manual_stadium.assert_called_once()
                self.assertTrue(selector.prematch_panel)
                self.assertTrue(selector.opened)
            finally: selector.shutdown()

    def test_audio_function_keys_apply_scope_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector=audio_fixtures.MatchAudioTests().make_selector(Path(tmp))
            try:
                audio_fixtures.MatchAudioTests().open_audio(selector)
                runtime=selector.audio_panel.runtime
                runtime.apply_general=Mock(return_value=(.95,1))
                selector.handle(2,0); selector.handle(16,1)
                runtime.apply_general.assert_called_once_with((.95,1))
                audio_fixtures.MatchAudioTests().open_audio(selector)
                runtime.apply_match=Mock(return_value=(.9,1))
                selector.handle(2,0); selector.handle(2,0); selector.handle(16,2)
                runtime.apply_match.assert_called_once_with((.9,1))
                audio_fixtures.MatchAudioTests().open_audio(selector); selector.handle(16,3)
                self.assertFalse(selector.opened)
                self.assertEqual(runtime.apply_general.call_count,1)
                self.assertEqual(runtime.apply_match.call_count,1)
            finally: selector.shutdown()
