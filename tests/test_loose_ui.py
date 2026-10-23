import struct,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from server16_py.loose_ui import activate,PANORAMA_TARGETS,TARGETS

class LooseUITest(unittest.TestCase):
    def test_panorama_scope_includes_both_navigation_routes(self):
        self.assertIn('data/ui/nav/mainfeflow.nav',PANORAMA_TARGETS)
        self.assertIn('data/ui/nav/careermode/mainmenuhubflow.nav',PANORAMA_TARGETS)
        self.assertNotIn('data/ui/layout/careermanagerhubcfg.xml',PANORAMA_TARGETS)
        self.assertIn('data/ui/layout/careermanagerhubcfg.xml',TARGETS)
    def fixture(self,game):
        name='data/ui/game/screens/misc/stadiumpan.big';payload=game/name;payload.parent.mkdir(parents=True);payload.write_bytes(b'APT')
        names=['unrelated',name,'also/unrelated'];directory=b'';records=b''
        for i,value in enumerate(names):
            directory+=struct.pack('>II',512+i*16,16)+value.encode()+b'\0'
            records+=struct.pack('>IIIQ',512+i*16,16,i,0x12345678+i)
        archive=b'BIG4'+struct.pack('<I',560)+struct.pack('>II',3,16+len(directory))+directory
        (game/'data_front_end.big').write_bytes(archive+bytes(560-len(archive)))
        before=b'ViV4'+struct.pack('<I',76)+struct.pack('>II',3,76)+records
        index=game/'data_front_end.bh';index.write_bytes(before);return index,before
    def test_target_only_backup_idempotence_and_read_only_check(self):
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp);index,before=self.fixture(game)
            self.assertEqual(activate(game,True)['status'],'activation_required');self.assertEqual(index.read_bytes(),before)
            self.assertEqual(activate(game)['changed'],1)
            self.assertEqual(index.read_bytes(),before[:48]+bytes(8)+before[56:])
            self.assertEqual(next((game/'ModCarrerMode/backups').glob('*/data_front_end.bh')).read_bytes(),before)
            self.assertEqual(activate(game)['changed'],0)
            self.assertEqual(activate(game,True,targets={'unrelated/missing'})['entries'],0)
    def test_mismatched_order_has_no_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp);index,before=self.fixture(game);bad=bytearray(before);struct.pack_into('>I',bad,16,999);index.write_bytes(bad)
            with self.assertRaises(ValueError):activate(game)
            self.assertEqual(index.read_bytes(),bad)
    def test_write_failure_restores_the_original_index(self):
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp);index,before=self.fixture(game)
            with patch('server16_py.loose_ui.os.fsync',side_effect=OSError('disk write failed')):
                with self.assertRaises(OSError):activate(game)
            self.assertEqual(index.read_bytes(),before)
