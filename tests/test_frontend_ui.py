"""Regressions for headers that a lenient APT VM accepts but FIFA crashes on."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_frontend_ui as builder
from validate_frontend_ui import validate_native_headers,main as validate_behavior
from formats import AptFile,BigFile,Reader
from apt_actions import Actions

class FrontendNativeHeaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='fifa_apt_header_')
        cls.folder=Path(cls.temp.name)
        for name,kind in [('backgroundfifa','background'),('stadiumpan','panorama')]:
            builder.build(ROOT/'native_mods/frontend_stadium/ui_templates'/f'{name}.big',cls.folder/f'{name}.big',kind)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def actions(self,name):return Actions(AptFile(BigFile(self.folder/f'{name}.big'))).read_all()

    def test_generated_ui_native_headers_and_behavior(self):validate_behavior(self.folder)

    def test_null_function_name_rejected(self):
        actions=self.actions('backgroundfifa')
        wrapper=next(i for block in actions.cache.values() for i in block
                     if i.op==142 and i.value['params']==[(2,'server16Argument')])
        reader=Reader(actions.apt.data,wrapper.offset+1,8);reader.align()
        struct.pack_into('<Q',actions.apt.data,reader.pos,0)
        with self.assertRaisesRegex(ValueError,'name pointer'):validate_native_headers(actions)

    def test_register_underallocation_rejected(self):
        actions=self.actions('stadiumpan')
        wrapper=next(i for block in actions.cache.values() for i in block
                     if i.op==142 and i.value['params']==[(2,'server16Argument')])
        reader=Reader(actions.apt.data,wrapper.offset+1,8);reader.ptr()
        reader.pos=(reader.pos+3)//4*4;reader.i()
        struct.pack_into('<h',actions.apt.data,reader.pos,5)
        with self.assertRaisesRegex(ValueError,'register allocation'):validate_native_headers(actions)

if __name__=='__main__':unittest.main()
