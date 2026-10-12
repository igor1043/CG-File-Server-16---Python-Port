import struct
import unittest
from server16_py.narration_bank import HarmonyBank,sps_size

class NarrationBankTests(unittest.TestCase):
    def field(self,kind,flags,base,values=b'',count=4):
        data=bytearray(80)+values
        data[53]=kind;struct.pack_into('<HQI',data,54,flags,base,80)
        bank=HarmonyBank.__new__(HarmonyBank);bank.data=bytes(data);bank.endian='<'
        return bank.field(48,count)
    def test_packed_indices_keep_nonconsecutive_aliases(self):
        self.assertEqual(self.field(3,0x202,3,struct.pack('<HHH',100,200,300)+bytes([132])),[100,200,100,300])
    def test_signed_stride_and_compressed_offsets(self):
        self.assertEqual(self.field(1,0xfffc,100),[100,96,92,88])
        self.assertEqual(self.field(2,0x105,256,bytes([1,2,2,4])),[288,320,320,384])
    def test_truncated_and_invalid_index_tables_are_rejected(self):
        for values in (struct.pack('<HHH',100,200,300),struct.pack('<HHH',100,200,300)+bytes([255])):
            with self.assertRaises(ValueError):self.field(3,0x202,3,values)
    def test_audio_ends_before_the_next_occurrence(self):
        sps=bytes.fromhex('4800000c')+bytes(8)+bytes.fromhex('44000008')+bytes(4)+bytes.fromhex('45000000')
        self.assertEqual(sps_size(sps+sps),(0,len(sps)))
        with self.assertRaises(ValueError):sps_size(sps[:-2])
        with self.assertRaises(ValueError):sps_size(sps[:-4]+bytes.fromhex('450000ff'))

if __name__=='__main__':unittest.main()
