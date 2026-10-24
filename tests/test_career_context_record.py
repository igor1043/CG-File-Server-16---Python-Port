"""Read-only context stays usable after deferred card owners are cleared."""
import struct,unittest
from types import SimpleNamespace
from unittest.mock import patch
from server16_py.career_context import _career_service_active


class ContextRecordTests(unittest.TestCase):
    def setUp(self):
        self.g=0x140000000;self.record=0x71000000;self.service=0x80000000;self.registry=0x81000000;self.context=0x82000000
        self.seq=2;self.pid=123;self.vtable=0x140123456;self.club=1629;self.selected=0;self.torn=False;self.reads=0
        self.m=SimpleNamespace(base_module=self.g,process_id=123,read_process_memory=self.read,
                               read_int64=lambda a:struct.unpack('<Q',self.read(a,8))[0],
                               read_uint32=lambda a:struct.unpack('<I',self.read(a,4))[0])
    def read(self,a,n):
        if a==self.g+0x5aafff0:return bytes.fromhex('4863411483f8ff750331c0c34869c01803000048034118c3')
        if a==self.g+0x5ac5940:return bytes.fromhex('83fa0177114863c2486bc0744805a00100004801c8c3')
        if a==self.g+0x44575e0:return bytes(7)+b'\xc7\x01'+struct.pack('<I',121)+bytes(11)
        if a==self.record:
            self.reads+=1
            return struct.pack('<IIIIQQQII',1,48,self.seq+(2 if self.torn and self.reads>1 else 0),self.pid,self.service,self.vtable,self.registry,7,456)
        values={self.registry+121*32+24:0x83000000,0x83000000:self.service,self.service:self.vtable,
                self.service+0x14:self.selected,self.service+0x18:self.context,self.context+0x1a4:self.club,self.context+0x18c:1}
        if a not in values:raise RuntimeError(hex(a))
        return struct.pack('<I' if n==4 else '<Q',values[a]&((1<<(n*8))-1))
    def profile(self):
        with patch('server16_py.career_context._export',side_effect=lambda m,b,s,n:self.record if n==b'Fifa16CareerContextRead' else None):
            return _career_service_active(self.m,[(0x70000000,0x200000)],True)
    def test_finance_and_preview_need_no_retained_stats_owner(self):
        p=self.profile();self.assertEqual(p['club_id'],1629);self.assertEqual(p['context_address'],self.context);self.assertEqual(p['context_epoch'],7)
    def test_incomplete_foreign_and_torn_records_are_rejected(self):
        self.seq=3;self.assertIsNone(self.profile())
        self.seq=2;self.pid=124;self.assertIsNone(self.profile())
        self.pid=123;self.torn=True;self.reads=0;self.assertIsNone(self.profile())
    def test_actual_selected_context_is_rechecked(self):
        self.selected=-1;self.assertIs(self.profile(),False)
        self.selected=8;self.assertIsNone(self.profile())
        self.selected=0;self.club=0;self.assertIs(self.profile(),False)

if __name__=='__main__':unittest.main()
