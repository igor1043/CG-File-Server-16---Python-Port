from pathlib import Path
import ctypes,hashlib,json,os,shutil,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from server16_py import scoreboard_options as score,movie_options as movies
from server16_py import stadium_options as stadium

def asset_source():
    configured=os.environ.get('SERVER16_TEST_ASSET_ROOT')
    source=Path(configured)/'ModCarrerMode/source' if configured else Path(__file__).resolve().parents[1]
    if not (source/'native_mods/scoreboard_settings/gamesettings.original.big').is_file():raise unittest.SkipTest('Defina SERVER16_TEST_ASSET_ROOT para os testes dos arquivos nativos')
    return source

class Catalogs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'FSW').mkdir()
    def test_ini_addition_and_missing_packages_and_unrelated_invalid_ini(self):
        ini=self.root/'FSW/settings.ini'
        ini.write_text('[invalid]\n=broken legacy row\n[Scoreboard]\n1=Nova TV\n[Movies]\n1=Abertura nova\n',encoding='utf8')
        before=ini.read_bytes()
        self.assertEqual(score.discover(self.root).packages,());self.assertEqual(movies.discover(self.root).packages,())
        (self.root/'ScoreBoardGBD/Nova TV').mkdir(parents=True);(self.root/'MoviesGBD/Abertura nova').mkdir(parents=True)
        self.assertEqual(score.discover(self.root).packages,('Nova TV',));self.assertEqual(movies.discover(self.root).packages,('Abertura nova',))
        old=movies.discover(self.root).signature
        (self.root/'MoviesGBD/Outra').mkdir();ini.write_text(ini.read_text()+'2=Outra\n',encoding='utf8')
        self.assertNotEqual(movies.discover(self.root).signature,old)
        (self.root/'MoviesGBD/Abertura nova').rmdir()
        self.assertEqual(movies.discover(self.root).packages,('Outra',))
        self.assertTrue(before.startswith(b'[invalid]'))
    def test_aliases_are_deduplicated_and_choice_resolves_to_installed_package(self):
        from server16_py.competition_catalog import PRESENTATION_ALIASES
        (self.root/'MoviesGBD/Physical').mkdir(parents=True)
        path=self.root/PRESENTATION_ALIASES;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('movies|TV no INI|Physical\n',encoding='utf8')
        (self.root/'FSW/settings.ini').write_text('[Movies]\n1=TV no INI\n')
        self.assertEqual(movies.discover(self.root).packages,('TV no INI',))
        movies.save_choice(self.root,'TV no INI');self.assertEqual(movies.load_choice(self.root),'TV no INI')
        with self.assertRaises(ValueError):movies.save_choice(self.root,'../outside')
    def test_movie_request_rejects_stale_session_and_catalog(self):
        (self.root/'MoviesGBD/TV').mkdir(parents=True);p=self.root/movies.REQUEST;p.parent.mkdir(parents=True)
        cat=movies.discover(self.root)
        def write(pid=12,signature=cat.signature,index=2):p.write_text(f'schema=1\npid={pid}\ncreated=12345\nwire=S16MOVIE1|{signature}|{index}|END\n')
        write();self.assertEqual(movies.read_request(self.root,12,12345)[1],2)
        for kwargs in ({'pid':13},{'signature':'f'*64},{'index':99}):
            write(**kwargs)
            with self.assertRaises(ValueError):movies.read_request(self.root,12,12345)
    def test_native_options_scope_does_not_leak_to_another_match(self):
        app=SimpleNamespace(_kickoff_generation=1,HID='1043',AID='123',TOURNAME='7',TOURROUNDID='71',lastpagename=stadium.PAGE,memory=SimpleNamespace(is_open=lambda:True))
        app._native_stadium_options_context=stadium.context(app);self.assertTrue(stadium.owns_settings(app))
        app._kickoff_generation=2;self.assertFalse(stadium.owns_settings(app))
        app._native_stadium_options_context=stadium.context(app);app._stadium_fixture_entered=True;self.assertFalse(stadium.owns_settings(app))
    def test_refresh_is_entry_bound_and_never_changes_saved_games(self):
        app=SimpleNamespace(exedir=self.root,memory=SimpleNamespace(process_id=12));entry={'pid':'12','created':'12345','captured_tick':'999'}
        stadium.publish_refresh(app,entry);p=self.root/stadium.RUNTIME/'refresh.tsv';text=p.read_text()
        self.assertIn('entry_tick=999',text);self.assertIn('pid=12',text)
        before=p.read_bytes();app.memory.process_id=13;stadium.publish_refresh(app,entry);self.assertEqual(before,p.read_bytes())

class NativeUI(unittest.TestCase):
    def test_reentering_settings_rebuilds_only_when_the_ini_catalog_changes(self):
        from server16_py import scoreboard_options_ui as ui
        import sys
        source=asset_source();env=source/'club_environment'
        sys.path[:0]=[str(env/'vendor'),str(env/'bank'),str(env/'preview'),str(env)]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);relative='ModCarrerMode/source/native_mods/scoreboard_settings/gamesettings.original.big'
            target=root/relative;target.parent.mkdir(parents=True);shutil.copy2(source/'native_mods/scoreboard_settings/gamesettings.original.big',target)
            (root/'FSW').mkdir();(root/'ScoreBoardGBD/A').mkdir(parents=True)
            app=SimpleNamespace(exedir=root,memory=SimpleNamespace(process_id=12),log=Mock());service=score.ScoreboardOptions(app);service.root=root
            try:
                with patch.object(ui,'build',wraps=ui.build) as builder:
                    service._prepare(root);self.assertTrue(service.bound);self.assertEqual(builder.call_count,1)
                    service._prepare(root);self.assertEqual(builder.call_count,1)
                    (root/'ScoreBoardGBD/B').mkdir();(root/'FSW/settings.ini').write_text('[Scoreboard]\n7=B\n')
                    service._prepare(root,{'pid':'12','created':'123','captured_tick':'999'})
                    self.assertEqual(builder.call_count,2);self.assertEqual(json.loads((root/score.CATALOG).read_bytes())['packages'],['A','B'])
                    self.assertTrue((root/stadium.RUNTIME/'refresh.tsv').is_file());app.log.assert_not_called()
            finally:service.close()
    def test_single_stadium_photo_preserves_all_native_resources_and_both_initial_values(self):
        from server16_py.scoreboard_options_ui import build
        from PIL import Image
        source=asset_source()
        import sys
        env=source/'club_environment';sys.path[:0]=[str(env/'vendor'),str(env/'bank'),str(env/'preview'),str(env)]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);relative='ModCarrerMode/source/tools/career_branding/originals/careerhubwidget.big'
            target=root/relative;target.parent.mkdir(parents=True);shutil.copy2(source/'tools/career_branding/originals/careerhubwidget.big',target)
            photo=root/'photo.png';Image.new('RGB',(1200,350),'green').save(photo)
            (root/'MoviesGBD/TV').mkdir(parents=True);movies.save_choice(root,'TV')
            original=source/'native_mods/scoreboard_settings/gamesettings.original.big'
            output=root/score.UI_PATH
            record=build(root,original,output,root/score.CATALOG,{'id':176,'title':'Estádio escolhido','preview':str(photo)})
            from formats import AptFile,BigFile
            native=BigFile(original);built=BigFile(output)
            for name,entry in native.entries.items():
                if name!='0':self.assertEqual(entry.data,built.entries[name].data,name)
            apt=AptFile(built);self.assertEqual(apt.stage_width,1280)
            self.assertIn('S16StadiumPhoto',[getattr(c,'name',None) for c in apt.characters[apt.exports['game.screens.settings.GameSettings']].frames[0]])
            score.verified_ui(root,record);movies.save_choice(root,None);score.update_movie_initial(root,movies.discover(root));score.verified_ui(root,record)
    def test_nav_is_idempotent_and_only_reloads_native_view(self):
        from server16_py.stadium_options_nav import patch as patch_nav,refresh_actions
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'flow.nav';data={'name':'Flow','states':[{'name':'SettingsGame','onEnter':[['loadView',['screen',stadium.PAGE]]]}]}
            p.write_text(json.dumps(data));patch_nav(p);first=p.read_bytes();patch_nav(p);self.assertEqual(first,p.read_bytes())
            row=json.loads(first)['states'][0]['transitions'][0];self.assertEqual(row['actions'],refresh_actions());self.assertNotIn('targets',row)

if __name__=='__main__':unittest.main()
