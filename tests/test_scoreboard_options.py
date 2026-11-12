from pathlib import Path
import hashlib,json,os,struct,sys,tempfile,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from server16_py import scoreboard_options as options


class Selection(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        for name in ('A - Placar','B - Taça do Brasil'):(self.root/'ScoreBoardGBD'/name).mkdir(parents=True)
    def request(self,index=2,pid=42,created=123456,signature=None):
        path=self.root/options.REQUEST;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(f'schema=1\npid={pid}\ncreated={created}\nwire=S16SCORE1|{signature or options.discover(self.root).signature}|{index}|END\n',encoding='ascii')
    def test_catalog_uses_the_same_installed_packages_and_safe_names(self):
        catalog=options.discover(self.root)
        self.assertEqual(catalog.values,(None,'','A - Placar','B - Taça do Brasil'))
        self.assertEqual(len(catalog.signature),64)
        for value in ('../outside','a/b','x\\y','C:outside','..','x\n',''):
            self.assertFalse(options.valid_name(value))
    def test_preference_does_not_change_competition_assignments_or_saved_games(self):
        settings=self.root/'settings.ini';settings.write_bytes(b'[Scoreboard]\n100=B - Ta\xe7a\n')
        saved=self.root/'CareerSave';saved.write_bytes(b'original save')
        for choice,expected in ((None,'assigned'),('A - Placar','A - Placar'),('','')):
            options.save_choice(self.root,choice);self.assertEqual(options.resolve(self.root,'assigned'),expected)
            self.assertEqual(options.load_choice(self.root),choice)
        self.assertEqual(settings.read_bytes(),b'[Scoreboard]\n100=B - Ta\xe7a\n');self.assertEqual(saved.read_bytes(),b'original save')
    def test_removed_or_invalid_package_cannot_escape_the_catalog(self):
        with self.assertRaises(ValueError):options.save_choice(self.root,'../outside')
        options.save_choice(self.root,'A - Placar');(self.root/'ScoreBoardGBD/A - Placar').rmdir()
        self.assertIsNone(options.load_choice(self.root))
    def test_only_the_matching_game_session_and_catalog_can_commit(self):
        self.request();catalog,index=options.read_request(self.root,42,123456);self.assertEqual(index,2)
        for kwargs in (dict(pid=43),dict(created=999999),dict(index=999),dict(signature='a'*64)):
            self.request(**kwargs)
            with self.assertRaises(ValueError):options.read_request(self.root,42,123456)
    def test_preference_is_recovered_in_another_service_instance(self):
        options.save_choice(self.root,'B - Taça do Brasil')
        self.assertEqual(options.selected_index(self.root,options.discover(self.root)),3)
    def test_changed_catalog_cannot_overwrite_a_concurrent_ui_integration(self):
        ui=self.root/options.UI_PATH;ui.parent.mkdir(parents=True);ui.write_bytes(b'other integration')
        manifest=self.root/options.CATALOG;manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps(dict(schema=1,signature='old',initial_value_offset=2,ui_stable_sha256='old')))
        app=SimpleNamespace(log=Mock());service=options.ScoreboardOptions(app)
        try:
            service.root=self.root;service._prepare(self.root)
            self.assertEqual(ui.read_bytes(),b'other integration');self.assertFalse(service.bound)
            app.log.assert_called_once()
        finally:service.close()
    def test_copy_is_queued_off_the_polling_thread_and_stale_requests_are_rejected(self):
        app=SimpleNamespace(memory=SimpleNamespace(process_id=42),log=Mock(),module_enabled=lambda name:True,apply_scoreboard_runtime=Mock())
        service=options.ScoreboardOptions(app)
        try:
            service.root=self.root;service.bound=True;service.owner_pid=42;self.request()
            with patch.object(options,'read_request',return_value=(options.discover(self.root),2)),patch.object(options,'update_initial_choice'),patch('psutil.Process') as process:
                process.return_value.create_time.return_value=0
                service.poll('other page')
                deadline=time.monotonic()+2
                while not app.apply_scoreboard_runtime.called and time.monotonic()<deadline:time.sleep(.01)
                app.apply_scoreboard_runtime.assert_called_once();self.assertEqual(options.load_choice(self.root),'A - Placar')
                service.poll('other page');app.apply_scoreboard_runtime.assert_called_once()
        finally:service.close()


class NativeScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=Path(os.environ.get('SERVER16_SOURCE_ROOT',Path(__file__).resolve().parents[1]));env=source/'club_environment'
        sys.path[:0]=[str(env/'vendor'),str(env/'bank'),str(env/'preview'),str(env)]
        from server16_py.scoreboard_options_ui import build
        from formats import BigFile,AptFile
        from apt_actions import Actions
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        for name in ('A - Placar','B - Copa'):(cls.root/'ScoreBoardGBD'/name).mkdir(parents=True)
        original=source/'native_mods/scoreboard_settings/gamesettings.original.big'
        cls.output=cls.root/options.UI_PATH
        cls.record=build(cls.root,original,cls.output,cls.root/options.CATALOG)
        before=AptFile(BigFile(original));after=AptFile(BigFile(cls.output));cls.exports_preserved=before.exports==after.exports
        def registration(apt):return next(c for c in apt.root_frames[0] if isinstance(c,tuple) and c[0]=='init' and c[1]==apt.exports['__Packages.game.screens.settings.GameSettings'])
        old=Actions(before).read_all().cache[registration(before)[-1]]
        new=Actions(after).read_all().cache[registration(after)[-1]]
        cls.code=new[len(old)-1:]
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        from apt_test_vm import NativeVM
        from apt_vm import Object,Native
        from server16_py.scoreboard_options_ui import ROW
        self.ROW=ROW;self.Object=Object;self.calls=[]
        def callback(name,owner,args):
            self.calls.append((name,tuple(args)))
            if name=='baseCurrent':return 23
            if name=='baseInput':return 'native'
            if name=='push':owner.extend(args)
        self.vm=NativeVM(callback);self.proto=Object({old:Native(new) for old,new in (
            ('InitGameSetting','baseInit'),('GetCurrentSettingValue','baseCurrent'),('GetDefaultSettingValue','baseDefault'),
            ('SetCurrentSettingValue','baseSet'),('OnChangeCallback','baseChange'),('LocalEventHandler','baseInput'),
            ('OnExitScreen','baseExit'),('ResetGameSettings','baseReset'))})
        klass=Object(dict(prototype=self.proto));self.vm.global_.set('game',Object(dict(screens=Object(dict(settings=Object(dict(GameSettings=klass)))))))
        self.vm.global_.set('Settings',Object(dict(eCategory=Object(dict(MATCH=10)))))
        self.vm.global_.set('INPUTCODE',Object(dict(BACK=1,ADVANCE=2,UI_RIGHT=3)))
        self.vm.global_.set('ION_CareerMode',Object(dict(SendSystemEvent=Native('SendSystemEvent'))))
        self.vm.run(self.code,self.vm.global_,self.vm.global_)
        self.match=Object(dict(settings=[11,12]));self.other=Object(dict(settings=[21,22]))
        self.view=Object(dict(mcData=Object(dict(categories=Object({10:self.match,20:self.other}),settings=Object()))),self.proto)
        self.invoke('InitGameSetting');self.calls.clear()
    def invoke(self,name,*args):return self.vm.invoke(self.proto.get(name),self.view,args)
    def test_all_original_exports_and_rows_are_preserved_with_extra_match_rows(self):
        self.assertTrue(self.exports_preserved);self.assertEqual(self.match.get('settings'),[11,12,self.ROW,65001,65002])
        self.assertEqual(self.other.get('settings'),[21,22]);self.invoke('InitGameSetting')
        self.assertEqual(self.match.get('settings'),[11,12,self.ROW,65001,65002])
        self.assertEqual(self.invoke('S16ScoreboardValues'),[0,1,2,3]);self.assertEqual(len(self.invoke('S16ScoreboardLabels')),4)
    def test_attendance_uses_native_toggle_and_commits_without_changing_scoreboard(self):
        labels=self.invoke('S16CrowdLabels')
        self.assertEqual(labels[0].encode('latin1').decode('utf8'),'Automático')
        self.assertEqual(labels[1:],[str(v)+'%' for v in range(0,101,5)])
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,65001),0)
        self.invoke('SetCurrentSettingValue',10,65001,14)
        self.invoke('OnChangeCallback',1,10,65001,14)
        self.assertEqual(self.calls,[])
        self.invoke('InitGameSetting')
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,65001),14)
        self.invoke('LocalEventHandler',1,0,0);self.invoke('OnExitScreen')
        messages=[args for name,args in self.calls if name=='SendSystemEvent']
        self.assertEqual(messages,[('GameSettings','Server16MatchCrowd','S16CROWD1|65|END')])
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,self.ROW),0)
    def test_native_controller_never_receives_the_custom_setting_id(self):
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,self.ROW),0)
        self.invoke('SetCurrentSettingValue',10,self.ROW,2);self.invoke('OnChangeCallback',1,10,self.ROW,2)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,11),23)
        self.invoke('SetCurrentSettingValue',10,11,4)
        self.assertEqual(self.calls,[('baseCurrent',(10,11)),('baseSet',(10,11,4))])
    def test_movie_row_commits_once_without_passing_its_id_to_native_controller(self):
        self.assertEqual(self.invoke('S16MovieValues'),[0,1])
        self.invoke('SetCurrentSettingValue',10,65002,1);self.invoke('OnChangeCallback',1,10,65002,1)
        self.assertEqual(self.calls,[])
        self.invoke('LocalEventHandler',1,0,0);self.invoke('OnExitScreen')
        messages=[args for name,args in self.calls if name=='SendSystemEvent']
        self.assertEqual(messages,[('GameSettings','Server16MatchMovie','S16MOVIE1|'+self.record['movie_signature']+'|1|END')])
    def test_stadium_shortcut_is_scoped_to_its_native_row(self):
        settings=self.vm.global_.get('Settings');settings.set('eSetting',self.Object(dict(STADIUM=11)))
        self.vm.global_.get('INPUTCODE').set('OPTION_LEFT',9)
        self.view.set('m_nSettingEnum',12);self.assertEqual(self.invoke('LocalEventHandler',9,0,0),'native')
        self.assertEqual([args for name,args in self.calls if name=='SendSystemEvent'],[])
        self.calls.clear();self.view.set('m_nSettingEnum',11)
        self.assertTrue(self.invoke('LocalEventHandler',9,0,0))
        self.assertEqual(self.calls,[('SendSystemEvent',('GameSettings','Server16OpenStadium','S16STADIUM1|OPEN|END'))])
    def test_commit_happens_once_on_back_and_stock_input_keeps_its_return_value(self):
        self.invoke('SetCurrentSettingValue',10,self.ROW,3);self.assertEqual(self.calls,[])
        self.assertEqual(self.invoke('LocalEventHandler',1,0,0),'native');self.invoke('OnExitScreen')
        messages=[args for name,args in self.calls if name=='SendSystemEvent']
        self.assertEqual(len(messages),1)
        self.assertEqual(messages[0],('GameSettings','Server16MatchScoreboard','S16SCORE1|'+self.record['signature']+'|3|END'))
    def test_native_category_refresh_does_not_discard_a_pending_choice(self):
        self.invoke('SetCurrentSettingValue',10,self.ROW,2)
        self.invoke('InitGameSetting');self.invoke('LocalEventHandler',1,0,0)
        messages=[args for name,args in self.calls if name=='SendSystemEvent']
        self.assertEqual(len(messages),1);self.assertTrue(messages[0][-1].endswith('|2|END'))
    def test_reset_and_invalid_toggle_values(self):
        self.invoke('SetCurrentSettingValue',10,self.ROW,2)
        for value in (-1,4,100000):self.invoke('SetCurrentSettingValue',10,self.ROW,value)
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,self.ROW),2)
        self.invoke('ResetGameSettings');self.assertEqual(self.invoke('GetCurrentSettingValue',10,self.ROW),0)
    def test_registration_is_idempotent(self):
        self.vm.run(self.code,self.vm.global_,self.vm.global_)
        self.assertEqual(self.invoke('LocalEventHandler',3,0,0),'native')
        self.assertEqual(self.calls,[('baseInput',(3,0,0))])
    def test_next_launch_initial_value_changes_only_the_owned_integer(self):
        original=self.output.read_bytes();options.save_choice(self.root,'A - Placar')
        options.update_initial_choice(self.root,options.discover(self.root));changed=self.output.read_bytes();at=self.record['initial_value_offset']
        self.assertEqual(original[:at],changed[:at]);self.assertEqual(original[at+4:],changed[at+4:]);self.assertEqual(struct.unpack_from('<i',changed,at)[0],2)
        # An unrelated UI integration cannot be silently overwritten.
        corrupt=bytearray(changed);corrupt[-1]^=1;self.output.write_bytes(corrupt)
        with self.assertRaises(ValueError):options.update_initial_choice(self.root,options.discover(self.root))
        self.output.write_bytes(original);options.save_choice(self.root,None)

if __name__=='__main__':unittest.main()
