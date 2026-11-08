from pathlib import Path
import tempfile
import unittest
from server16_py.native_feature_switch import UltrawideSwitch, LowDrivenShotSwitch

class NativeFeatureSwitchTests(unittest.TestCase):
    def test_atomic_switch_preserves_other_options_and_sections(self):
        for switch_type in UltrawideSwitch,LowDrivenShotSwitch:
            with tempfile.TemporaryDirectory() as directory:
                switch=switch_type(directory)
                switch.ini.parent.mkdir(parents=True)
                dll=switch.mods/switch.module;dll.parent.mkdir(parents=True,exist_ok=True);dll.touch()
                original=f'; test\r\n[{switch.feature}]\r\nenabled=1 ; keep\r\nshoot_button=X\r\n[other]\r\nenabled=1\r\n'.encode()
                switch.ini.write_bytes(original)
                self.assertTrue(switch.available());self.assertTrue(switch.enabled())
                switch.set_enabled(False);self.assertFalse(switch.enabled())
                self.assertEqual(switch.ini.read_bytes(),original.replace(b'enabled=1 ; keep',b'enabled=0 ; keep'))
                switch.set_enabled(True);self.assertEqual(switch.ini.read_bytes(),original)
    def test_missing_module_is_not_silently_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            switch=UltrawideSwitch(directory)
            self.assertFalse(switch.enabled())
            with self.assertRaises(FileNotFoundError):switch.set_enabled(True)
    def test_malformed_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            switch=LowDrivenShotSwitch(directory);switch.ini.parent.mkdir(parents=True)
            (switch.mods/switch.module).touch();switch.ini.write_bytes(b'[other]\nenabled=1\n')
            with self.assertRaises(ValueError):switch.set_enabled(False)
            self.assertEqual(switch.ini.read_bytes(),b'[other]\nenabled=1\n')

if __name__=='__main__':unittest.main()
