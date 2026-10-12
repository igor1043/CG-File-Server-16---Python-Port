import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/narration_studio'))
import core,match_club_names

class ClubNameTests(unittest.TestCase):
    def test_equal_spoken_names_match_across_different_ids_and_preserve_manual_choices(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog=Path(temporary)/'catalog.sqlite';db=core.connect(catalog)
            db.execute("INSERT INTO banks(key,name,active) VALUES ('bank','bank',1)")
            for key,offset,text in [('original',100,'São Paulo!'),('alias',100,'São Paulo!'),('manual',200,'São Paulo!'),('different',300,'Santos')]:
                db.execute('INSERT INTO clips(key,bank,offset,transcript,topic) VALUES (?,?,?,?,?)',(key,'bank',offset,text,'Nomes de clubes'))
            db.execute('INSERT INTO sources(key,narrator,path,transcript,topic) VALUES (?,?,?,?,?)',('pes_99999','Custom','audio.flac','Sao Paulo','Nomes de clubes'))
            db.execute("INSERT INTO mappings VALUES ('Custom','manual','manual_source','manual',1)");db.commit();db.close()
            with patch.object(match_club_names,'connect',lambda:core.connect(catalog)):
                report=match_club_names.run('Custom')
            self.assertEqual(report['club_occurrences'],2)
            db=core.connect(catalog);mapped=dict(db.execute('SELECT clip,source FROM mappings'))
            self.assertEqual(mapped['original'],'pes_99999');self.assertEqual(mapped['alias'],'pes_99999')
            self.assertEqual(mapped['manual'],'manual_source');self.assertNotIn('different',mapped);db.close()

if __name__=='__main__':unittest.main()
