import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server16_py.ultrawide_background import (
    apply_background, read_dds, NATIVE, VARIANTS, STANDARD, WIDE, NOTFOUND, PRESSSTART,
)
from server16_py.native_feature_switch import UltrawideSwitch

def dds(width, height, colour):
    header=bytearray(128);header[:4]=b'DDS '
    for offset,value in [(4,124),(12,height),(16,width),(76,32)]:struct.pack_into('<I',header,offset,value)
    header[84:88]=b'DXT5'
    return bytes(header)+bytes([colour])*(((width+3)//4)*((height+3)//4)*16)

def pressstart(colour):
    entries = ((b'0', b'layout'), (b'1', b'control'), (b'2', dds(64, 64, colour)))
    directory_end = 16 + sum(9 + len(name) for name, _ in entries)
    offset = directory_end
    directory = bytearray()
    for name, content in entries:
        directory.extend(struct.pack('>II', offset, len(content)) + name + b'\0')
        offset += len(content)
    return b'BIG4' + struct.pack('<I', offset) + struct.pack('>II', len(entries), directory_end) + directory + b''.join(data for _, data in entries)

class UltrawideBackgroundTests(unittest.TestCase):
    def prepare(self,root):
        folder=root/VARIANTS;folder.mkdir(parents=True)
        standard,wide=dds(128,72,19),dds(192,72,27)
        (folder/STANDARD).write_bytes(standard);(folder/WIDE).write_bytes(wide)
        switch=UltrawideSwitch(root);switch.ini.parent.mkdir(parents=True)
        switch.ini.write_bytes(b'[ultrawide]\r\nenabled=1\r\n')
        module=switch.mods/switch.module;module.parent.mkdir();module.touch()
        return switch,standard,wide
    def test_toggle_uses_exact_original_dds_and_preserves_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);switch,standard,wide=self.prepare(root)
            switch.sync_background();self.assertEqual((root/NATIVE).read_bytes(),wide)
            switch.set_enabled(False);self.assertEqual((root/NATIVE).read_bytes(),standard)
            switch.set_enabled(True);self.assertEqual((root/NATIVE).read_bytes(),wide)
            self.assertEqual((root/VARIANTS/STANDARD).read_bytes(),standard)
            self.assertEqual((root/VARIANTS/WIDE).read_bytes(),wide)
    def test_startup_respects_saved_choice_and_skips_unchanged_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);switch,_,_=self.prepare(root);switch.sync_background()
            stamp=(root/NATIVE).stat().st_mtime_ns
            switch.sync_background();self.assertEqual((root/NATIVE).stat().st_mtime_ns,stamp)
            switch.set_enabled(False)
            self.assertTrue(UltrawideSwitch(root).sync_background())
            self.assertFalse(UltrawideSwitch(root).enabled())
    def test_bad_or_missing_variant_never_overwrites_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);switch,standard,_=self.prepare(root);switch.set_enabled(False)
            (root/VARIANTS/WIDE).write_bytes(b'DDS truncated')
            with self.assertRaises(ValueError):switch.set_enabled(True)
            self.assertFalse(switch.enabled());self.assertEqual((root/NATIVE).read_bytes(),standard)
            (root/VARIANTS/WIDE).unlink();self.assertFalse(apply_background(root,True))
            self.assertEqual((root/NATIVE).read_bytes(),standard)
    def test_failed_write_rolls_back_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);switch,standard,_=self.prepare(root);switch.set_enabled(False)
            with patch('server16_py.ultrawide_background._atomic',side_effect=PermissionError('busy')):
                with self.assertRaises(PermissionError):switch.set_enabled(True)
            self.assertFalse(switch.enabled());self.assertEqual((root/NATIVE).read_bytes(),standard)
    def test_wrong_dimensions_and_truncated_payload_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);switch,standard,_=self.prepare(root);switch.set_enabled(False)
            (root/VARIANTS/WIDE).write_bytes(standard)
            with self.assertRaises(ValueError):switch.set_enabled(True)
            (root/VARIANTS/WIDE).write_bytes(dds(192,72,1)[:-1])
            with self.assertRaises(ValueError):read_dds(root/VARIANTS/WIDE)

    def test_startup_assets_follow_the_switch_and_roll_back_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            switch, standard, wide = self.prepare(root)
            normal_files = {NATIVE: standard, NOTFOUND: dds(128, 72, 9), PRESSSTART: pressstart(3)}
            wide_files = {NATIVE: wide, NOTFOUND: dds(192, 72, 8), PRESSSTART: pressstart(4)}
            for mode, files in (('standard', normal_files), ('ultrawide', wide_files)):
                for target, data in files.items():
                    (root / VARIANTS / f'{target.stem}_{mode}{target.suffix.lower()}').write_bytes(data)
            switch.set_enabled(False)
            for target, data in normal_files.items():
                self.assertEqual((root / target).read_bytes(), data)

            from server16_py.ultrawide_background import _atomic
            def fail_on_pressstart(path, data):
                if path.name == PRESSSTART.name:
                    raise PermissionError('pressstart is in use')
                _atomic(path, data)
            with patch('server16_py.ultrawide_background._atomic', side_effect=fail_on_pressstart):
                with self.assertRaises(PermissionError):
                    switch.set_enabled(True)
            self.assertFalse(switch.enabled())
            for target, data in normal_files.items():
                self.assertEqual((root / target).read_bytes(), data)

            switch.set_enabled(True)
            for target, data in wide_files.items():
                self.assertEqual((root / target).read_bytes(), data)
            switch.set_enabled(False)
            for target, data in normal_files.items():
                self.assertEqual((root / target).read_bytes(), data)

if __name__=='__main__':unittest.main()
