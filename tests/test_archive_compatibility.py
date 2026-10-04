"""Portable ZIP cases and explicit failure modes for the production extractor."""
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from server16_py.file_tools import extract_archive


class ZipCompatibilityTests(unittest.TestCase):
    def test_stored_and_deflated_unicode_paths_spaces_and_empty_folders(self):
        for compression in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive=root/'Estádio Flamengo.zip'
                with zipfile.ZipFile(archive,'w',compression=compression) as z:
                    z.writestr('BRA - Maracanã - Flamengo/EntranceScene/',b'')
                    z.writestr('BRA - Maracanã - Flamengo/model.rx3',b'valid model payload'*400)
                self.assertEqual(extract_archive(archive,root/'output'),'ZIP')
                self.assertEqual((root/'output/BRA - Maracanã - Flamengo/model.rx3').read_bytes(),b'valid model payload'*400)
                self.assertTrue((root/'output/BRA - Maracanã - Flamengo/EntranceScene').is_dir())

    def test_zip64_stream_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'zip64.zip'
            with zipfile.ZipFile(archive,'w') as z:
                with z.open('model.rx3','w',force_zip64=True) as member:member.write(b'zip64 model')
            extract_archive(archive,root/'output')
            self.assertEqual((root/'output/model.rx3').read_bytes(),b'zip64 model')

    def test_crc_corruption_is_reported_as_failure_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'corrupt.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as z:z.writestr('model.rx3',b'known model bytes')
            payload=bytearray(archive.read_bytes())
            index=payload.index(b'known model bytes');payload[index]^=0xFF
            archive.write_bytes(payload)
            with self.assertRaises(zipfile.BadZipFile):extract_archive(archive,root/'output')

    def test_unsupported_method_and_encrypted_zip_fail_explicitly(self):
        for mode,error in (('compression',NotImplementedError),('password',RuntimeError)):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive=root/'unsupported.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr('model.rx3',b'payload')
                payload=bytearray(archive.read_bytes());central=payload.index(b'PK\x01\x02')
                if mode=='compression':
                    struct.pack_into('<H',payload,8,99);struct.pack_into('<H',payload,central+10,99)
                else:
                    struct.pack_into('<H',payload,6,1);struct.pack_into('<H',payload,central+8,1)
                archive.write_bytes(payload)
                with self.assertRaises(error):extract_archive(archive,root/'output')

    def test_absolute_drive_unc_and_parent_paths_cannot_escape_output(self):
        for name in ('../escape.rx3','C:/escape.rx3','\\\\server/share/escape.rx3','/escape.rx3'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive=root/'unsafe.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,b'payload')
                with self.assertRaisesRegex(RuntimeError,'Unsafe archive'):extract_archive(archive,root/'output')
                self.assertFalse((root/'escape.rx3').exists())


if __name__=='__main__':unittest.main()
