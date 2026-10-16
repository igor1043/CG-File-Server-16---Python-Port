from pathlib import Path
import re
import unittest
from server16_py.input_hints import PANEL_FUNCTION_KEYS, panel_function_key


class PanelFunctionKeysTests(unittest.TestCase):
    def test_labels_match_the_native_keyboard_dispatcher(self):
        source=Path(__file__).resolve().parents[1]/'server16_py/d3d_overlay/stadium_selector_bridge.cpp'
        text=source.read_text(encoding='utf-8')
        keys=re.search(r'action_keys\[\]=\{([^}]+)\}',text)[1]
        native=tuple('F'+number for number in re.findall(r'VK_F(\d+)',keys))
        self.assertEqual(native,PANEL_FUNCTION_KEYS)
        self.assertEqual(tuple(panel_function_key(i) for i in range(1,6)),('F3','F4','F5','F8','F9'))
        for i in (0,6):
            with self.assertRaises(ValueError):panel_function_key(i)

    def test_all_existing_panels_use_the_common_labels(self):
        root=Path(__file__).resolve().parents[1]/'server16_py'
        for name in ('prematch_panel.py','match_settings_panel.py','match_audio_panel.py','narration_panel.py','stadium_selector.py'):
            text=(root/name).read_text(encoding='utf-8')
            self.assertIn('panel_function_key',text,name)
            self.assertIsNone(re.search(r"['\"]F[12]['\"]|\bF[12]\b",text),name)

if __name__=='__main__':unittest.main()
