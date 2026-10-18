import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from server16_py.match_presentation import MatchPresentation, PresentationOptions
from server16_py.match_settings_panel import MatchSettingsPanel
import test_prematch_panel as fixtures
import test_match_audio_panel as audio_fixtures


class PresentationTests(unittest.TestCase):
    def test_opening_props_default_cancel_and_apply_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector = fixtures.PrematchTests().selector(Path(tmp))
            try:
                selector.open(hub=True); selector.handle(16, 3)
                panel = selector.prematch_panel
                self.assertTrue(panel.options.entrance_props)
                selector.handle(8, (280 << 16) | 500)
                self.assertFalse(panel.options.entrance_props)
                selector.handle(16, 2)
                self.assertTrue(MatchPresentation(tmp).load().entrance_props)
                selector.handle(16, 3)
                selector.prematch_panel.activate(4)
                selector.handle(16, 1)
                self.assertFalse(MatchPresentation(tmp).load().entrance_props)
            finally:
                selector.shutdown()

    def test_defaults_atomic_save_reload_and_other_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MatchPresentation(tmp)
            self.assertEqual(store.load(), PresentationOptions())
            self.assertFalse(store.path.exists())
            store.save(PresentationOptions(False, True, True, False))
            self.assertEqual(store.load(), PresentationOptions(False, True, True, False))
            with store.path.open('a', encoding='utf-8') as file:
                file.write('\n[unrelated]\nvalue=keep\n')
            store.save(PresentationOptions())
            self.assertIn('value = keep', store.path.read_text())
            self.assertFalse(list(store.path.parent.glob('*.tmp')))

    def test_invalid_config_and_replace_failure_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MatchPresentation(tmp)
            store.save(PresentationOptions())
            old = store.path.read_bytes()
            with patch('server16_py.match_presentation.os.replace', side_effect=PermissionError):
                with self.assertRaises(PermissionError):
                    store.save(PresentationOptions(False))
            self.assertEqual(old, store.path.read_bytes())
            with store.path.open('w', encoding='utf-8') as file:
                file.write('invalid file')
            with self.assertRaises(Exception):
                store.save(PresentationOptions())
            self.assertEqual(store.path.read_text(), 'invalid file')

    def test_hub_third_card_cancel_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector = fixtures.PrematchTests().selector(Path(tmp))
            try:
                selector.open(hub=True)
                selector.handle(16, 3)
                panel = selector.prematch_panel
                self.assertIsInstance(panel, MatchSettingsPanel)
                self.assertEqual(panel.options, PresentationOptions())
                selector.handle(6, 0)  # mascot off
                selector.handle(16, 2)  # cancel edits
                self.assertFalse(panel.store.path.exists())
                selector.handle(16, 3)
                panel = selector.prematch_panel
                self.assertTrue(panel.options.mascots)
                selector.handle(5, 0); selector.handle(6, 0)  # master on
                selector.handle(5, 0); selector.handle(6, 0)  # entrance on
                selector.handle(16, 1)
                self.assertEqual(panel.store.load(), PresentationOptions(True, True, True, False))
                self.assertFalse(selector.prematch_panel.crowd)
                selector.handle(16, 5)  # Back follows the narration card in the current hub.
                self.assertFalse(selector.opened)
            finally:
                selector.shutdown()

    def test_disabled_children_skip_focus_and_mouse_cannot_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector = fixtures.PrematchTests().selector(Path(tmp))
            try:
                selector.open(hub=True); selector.handle(16, 3)
                panel = selector.prematch_panel
                selector.handle(8, (193 << 16) | 500)
                self.assertFalse(panel.options.entrance)
                selector.handle(5, 0); selector.handle(5, 0)
                self.assertEqual(panel.focus, 4)
                panel.activate(1); panel.activate(2)
                self.assertTrue(panel.options.entrance)
                panel.activate(1)  # off keeps subchoice but disables its effective permission
                self.assertFalse(panel.enabled(2))
                panel.focus = 1
                selector.handle(5, 0)
                self.assertEqual(panel.focus, 4)
            finally:
                selector.shutdown()

    def test_live_controller_change_renders_without_resetting_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector = fixtures.PrematchTests().selector(Path(tmp))
            try:
                selector.handle(17, 1)  # connection delivered even when closed
                selector.open(hub=True); selector.handle(16, 3)
                panel = selector.prematch_panel
                panel.activate(0)
                with patch.object(selector, 'render') as render:
                    selector.handle(17, 0)
                    render.assert_called_once()
                    selector.handle(17, 0)
                    self.assertEqual(render.call_count, 1)
                self.assertIs(selector.prematch_panel, panel)
                self.assertFalse(panel.options.mascots)
            finally:
                selector.shutdown()

    def test_button_glyph_is_monochrome_and_not_drawn_on_hub_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector = fixtures.PrematchTests().selector(Path(tmp))
            try:
                selector.handle(17, 1); selector.open(hub=True)
                panel = selector.prematch_panel
                with patch('server16_py.input_hints.xbox_button') as glyph:
                    panel.render()
                    self.assertEqual([call.args[4] for call in glyph.call_args_list], ['A', 'B'])
                from server16_py.input_hints import xbox_button
                from server16_py.overlay_canvas import OverlayDraw
                from PIL import Image
                image = Image.new('RGBA', (80, 80), 'white')
                xbox_button(OverlayDraw(image), selector, 20, 20, 'Y')
                colors = set(image.getdata())
                for old_color in ((184, 134, 0, 255), (22, 132, 68, 255), (198, 50, 55, 255), (18, 99, 187, 255)):
                    self.assertNotIn(old_color, colors)
            finally:
                selector.shutdown()

    def test_audio_pad_scope_shortcuts(self):
        with tempfile.TemporaryDirectory() as tmp:
            selector = audio_fixtures.MatchAudioTests().make_selector(Path(tmp))
            try:
                selector.handle(17, 1); audio_fixtures.MatchAudioTests().open_audio(selector)
                runtime = selector.audio_panel.runtime
                runtime.apply_general = Mock(return_value=(1, 1))
                runtime.apply_match = Mock(return_value=(1, 1))
                selector.handle(18, 1)
                runtime.apply_general.assert_called_once()
                audio_fixtures.MatchAudioTests().open_audio(selector); selector.handle(18, 2)
                runtime.apply_match.assert_called_once()
                audio_fixtures.MatchAudioTests().open_audio(selector); selector.handle(7, 0)
                self.assertFalse(selector.opened)
                self.assertEqual(runtime.apply_general.call_count, 1)
                self.assertEqual(runtime.apply_match.call_count, 1)
            finally:
                selector.shutdown()
