import sys,struct,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
from projects import unpack,safe_name
from server16_py.narration_competitions import choose_profile,competitions
from generic_policy import female_reference

class ProjectTests(unittest.TestCase):
    def fixture(self,version):
        audio=b'\x48\0\0\x08abcd\x45\0\0\x04';bank='audiodata/speechdata/por_br/demo.sbs'.encode('utf-16le')
        head=b'F16NPK'+str(version).encode()+b'\0'
        if version==3:head+=struct.pack('<II',1,len(audio))+audio
        head+=struct.pack('<II',1,len(bank)//2)+bank+struct.pack('<I',2)
        for off in (32,64):head+=struct.pack('<QI',off,0 if version==3 else len(audio))+(b'' if version==3 else audio)
        return head,audio
    def test_old_and_pooled_packages_decode_the_same_complete_assets(self):
        with tempfile.TemporaryDirectory() as t:
            for version in (2,3):
                data,audio=self.fixture(version);p=Path(t)/'test.npack';p.write_bytes(data)
                rows=list(unpack(p));self.assertEqual([r[1] for r in rows],[32,64]);self.assertEqual([r[2] for r in rows],[audio,audio])
    def test_truncated_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            data,_=self.fixture(3);p=Path(t)/'bad.npack';p.write_bytes(data[:-1])
            with self.assertRaises(ValueError):list(unpack(p))
    def test_competition_reader_handles_unrelated_invalid_ini_and_named_rules(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'FSW').mkdir();(root/'FSW/settings.ini').write_text('[bad]\n=invalid\n[comp]\n1=Stadium\n[Scoreboard]\n1615=BRA - Brasileirao Serie A\n',encoding='utf8')
            values={r['id']:r['name'] for r in competitions(root)}
            self.assertEqual(values['1615'],'BRA - Brasileirao Serie A');self.assertIn('1',values)
    def test_competition_selection_avoids_last_narrator_and_unassigned(self):
        profiles=[dict(name='V',competitions=['1615']),dict(name='L',competitions=['1615']),dict(name='Other',competitions=['8'])]
        self.assertEqual(choose_profile(profiles,'1615','V')['name'],'L');self.assertIsNone(choose_profile(profiles,'44'))
    def test_female_player_is_filtered_but_ball_references_remain(self):
        for text in ('Ela perde a bola.','Defendeu a goleira.','Autoriza a juíza.','É dela de novo!'):
            self.assertTrue(female_reference(text),text)
        for text in ('Olha essa bola e a curva que ela fez.','Rola a bola, deixa ela rolar.','A equipe está pronta.'):
            self.assertFalse(female_reference(text),text)
    def test_invalid_project_name_is_rejected(self):
        with self.assertRaises(ValueError):safe_name('../outside')

if __name__=='__main__':unittest.main()
