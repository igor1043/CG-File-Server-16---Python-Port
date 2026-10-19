import io
import struct
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from server16_py.competition_icons import (COMP_OBJ, ICON_MAP, ICONS, CompetitionIconImporter, CompetitionIconService, convert, identities, resolve)

class CompetitionIconsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.game=Path(self.temp.name)
        for path,text in ((COMP_OBJ,'1761,3,C7,TrophyName_Abbr15_7,0\n1620,3,C229,TrophyName_Abbr15_229,0\n'),
                          (Path('FSW/settings.ini'),'[movies]\n1761=BRA - Brasileirao\n1620=BRA - Copa do Brasil\n')):
            target=self.game/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
        self.folder=self.game/ICONS;self.folder.mkdir(parents=True);self.messages=[]
        self.importer=CompetitionIconImporter(self.game,self.messages.append)
    def image(self,name='1761.png',color=(22,66,220,180)):
        path=self.folder/name;Image.new('RGBA',(300,150),color).save(path);return path
    def test_ini_id_is_the_artwork_filename(self):
        mapping,labels,aliases=identities(self.game)
        self.assertEqual(mapping,{1761:1761,1620:1620})
        for name in ('1761','1761 - name','c1761','BRA - Brasileirao'):self.assertEqual(resolve(name,mapping,aliases),1761)
        for name in ('7','229','../1761','unknown'):
            with self.assertRaises(ValueError):resolve(name,mapping,aliases)
    def test_same_source_generates_proportional_calendar_and_cards_without_big(self):
        source=self.image();original=source.read_bytes();self.assertEqual(self.importer.sync(force=True),1)
        for kind,side,limit in (('calendar',128,48),('cards',256,256)):
            target=self.folder/kind/'c1761.dds';im=Image.open(target).convert('RGBA');bounds=im.getchannel('A').getbbox()
            self.assertEqual(im.size,(side,side));self.assertLessEqual(bounds[2],limit);self.assertLessEqual(bounds[3],limit)
            self.assertAlmostEqual((bounds[2]-bounds[0])/(bounds[3]-bounds[1]),2,delta=.15)
            self.assertEqual(target.read_bytes()[84:88],b'DXT5')
            self.assertEqual(struct.unpack_from('<I',target.read_bytes(),20)[0],side*side)
            self.assertEqual(struct.unpack_from('<I',target.read_bytes(),88)[0],0)
        self.assertEqual(source.read_bytes(),original);self.assertEqual(list(self.game.rglob('*.big')),[])
        self.assertIn('1761\t7\tBRA', (self.folder/'competitions.tsv').read_text())
    def test_two_views_are_repaired_without_a_runtime_state_file(self):
        self.image();self.importer.sync(force=True)
        (self.folder/'cards/c1761.dds').unlink();self.assertEqual(self.importer.sync(force=True),1)
        self.assertTrue((self.folder/'cards/c1761.dds').is_file());self.assertEqual(self.importer.sync(force=True),0)
    def test_changed_art_updates_both_views_and_preserves_backup(self):
        self.image();self.importer.sync(force=True);old=(self.folder/'cards/c1761.dds').read_bytes()
        self.image(color=(255,20,20,255));self.assertEqual(self.importer.sync(force=True),1)
        self.assertNotEqual(old,(self.folder/'cards/c1761.dds').read_bytes())
        self.assertTrue(any(p.read_bytes()==old for p in (self.game/'runtime/backups').rglob('c1761.dds')))
    def test_no_writes_while_game_is_running(self):
        self.image();service=CompetitionIconService(self.messages.append);service.poll(self.game,game_running=True)
        self.assertIsNone(service.worker);self.assertFalse((self.folder/'cards').exists());self.assertEqual(service.prepare(self.game,force=True),1)
    def test_stable_copy_and_old_visual_outputs_are_not_inputs(self):
        self.image();(self.folder/'c7.dds').write_bytes(b'old visual resource')
        self.assertEqual(self.importer.sync(),0);self.assertEqual(self.importer.sync(),1)
        self.assertEqual((self.folder/'c7.dds').read_bytes(),b'old visual resource')
    def test_duplicate_sources_and_invalid_art_do_not_publish(self):
        self.image();self.image('c1761.png');self.image('1620.png',(0,0,0,0))
        self.assertEqual(self.importer.sync(force=True),0);self.assertFalse((self.folder/'cards/c1761.dds').exists())
        self.assertTrue(self.messages)
    def test_empty_views_are_transparent_and_known_missing_art_is_not_substituted(self):
        self.importer.sync(force=True)
        for kind in ('calendar','cards'):
            p=self.folder/kind/'empty.dds';image=Image.open(p).convert('RGBA')
            self.assertIsNone(image.getchannel('A').getbbox())
            self.assertEqual(struct.unpack_from('<I',p.read_bytes(),20)[0],image.width*image.height)
        self.assertFalse((self.folder/'cards/c1620.dds').exists())
    def test_ambiguous_names_rejected_and_sources_keep_independent_ids(self):
        with (self.game/'FSW/settings.ini').open('a') as f:f.write('1620=BRA - Brasileirao\n')
        mapping,_,aliases=identities(self.game)
        with self.assertRaises(ValueError):resolve('BRA - Brasileirao',mapping,aliases)
        self.image('1761.png');self.image('1620.png');self.assertEqual(self.importer.sync(force=True),2)

if __name__=='__main__':unittest.main()
