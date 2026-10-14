import sys,struct,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
import core,projects
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
    def test_review_checkmarks_are_saved_and_restored_with_the_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);catalog=root/'catalog.sqlite';db=core.connect(catalog)
            db.execute("INSERT INTO clips(key,event,row,wav,status,transcript,topic) VALUES ('clip','INTRO',0,'original.wav','decoded','Original','Abertura e apresentação')")
            db.execute("INSERT INTO narration_reviews(profile,clip,reviewed) VALUES ('Custom','clip',1)");db.commit();db.close()
            projects_root=root/'projects';game=root/'game'
            with patch.object(projects,'connect',lambda:core.connect(catalog)),patch.object(projects,'PROJECTS',projects_root),patch.object(projects,'GAME',game):
                folder=projects.save('Custom')
                saved=json.loads((folder/'project.json').read_text(encoding='utf8'))
                self.assertEqual(saved['reviewed'],['clip'])
                db=core.connect(catalog);db.execute("DELETE FROM narration_reviews WHERE profile='Custom'");db.commit();db.close()
                projects.open_project(folder)
                db=core.connect(catalog)
                self.assertEqual(db.execute("SELECT reviewed FROM narration_reviews WHERE profile='Custom' AND clip='clip'").fetchone()[0],1)
                db.close()

    def test_editable_project_is_autosaved_beside_game_profile_and_can_be_reopened(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);catalog=root/'catalog.sqlite';audio=root/'voice.wav';audio.write_bytes(b'voice')
            db=core.connect(catalog)
            db.execute("INSERT INTO clips(key,event,row,wav,status,transcript,topic) VALUES ('clip','INTRO',0,'original.wav','decoded','Original','Abertura e apresentação')")
            db.execute("INSERT INTO sources(key,narrator,path,event,variant,transcript,duration,topic) VALUES ('source','Custom',?,'INTRO',0,'Minha apresentação',1.0,'Abertura e apresentação')",(str(audio),))
            db.execute("INSERT INTO mappings(profile,clip,source,method,score) VALUES ('Custom','clip','source','manual',1)")
            db.commit();db.close()
            projects_root=root/'projects';game=root/'game'
            with patch.object(projects,'connect',lambda:core.connect(catalog)),patch.object(projects,'PROJECTS',projects_root),patch.object(projects,'GAME',game):
                projects.save('Custom')
                installed=game/'Narrations'/'Custom';sidecar=installed/'Studio'/'project.json'
                self.assertTrue(sidecar.is_file())
                saved=json.loads(sidecar.read_text(encoding='utf8'))
                self.assertEqual(saved['mappings'][0]['source'],'source')
                db=core.connect(catalog);db.execute("DELETE FROM mappings WHERE profile='Custom'");db.commit();db.close()
                projects.open_project(installed)
                db=core.connect(catalog)
                self.assertEqual(db.execute("SELECT source FROM mappings WHERE profile='Custom' AND clip='clip'").fetchone()[0],'source')
                db.close()

if __name__=='__main__':unittest.main()
