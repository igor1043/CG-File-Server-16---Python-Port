"""Contract after removing the in-game scoreboard selector."""
import json,os,sys,unittest,tempfile
from pathlib import Path
from server16_py import scoreboard_options as options

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
        cls.code=new[len(old)-1:];cls.original_actions=len(old)-1
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

    def test_original_rows_and_exports_survive_without_scoreboard(self):
        self.assertTrue(self.exports_preserved)
        self.assertEqual(self.match.get('settings'),[11,12,65001,65002])
        self.assertEqual(self.other.get('settings'),[21,22])
        self.assertIsNone(self.view.get('mcData').get('settings').get(65000))
        self.assertIs(self.record['scoreboard_selectable'],False)

    def test_registration_and_reentry_are_idempotent(self):
        self.invoke('InitGameSetting');self.invoke('InitGameSetting')
        self.assertEqual(self.match.get('settings'),[11,12,65001,65002])

    def test_removed_row_delegates_to_original_native_behavior(self):
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,65000),23)
        self.invoke('OnChangeCallback',10,1,65000,2)
        self.assertFalse(any(n=='SendSystemEvent' and 'Server16MatchScoreboard' in a for n,a in self.calls))

    def test_attendance_still_emits_only_attendance_event(self):
        self.invoke('SetCurrentSettingValue',10,65001,3)
        self.invoke('OnExitScreen')
        events=[a for n,a in self.calls if n=='SendSystemEvent']
        self.assertTrue(any('Server16MatchCrowd' in a for a in events))
        self.assertFalse(any('Server16MatchScoreboard' in a for a in events))

    def test_movie_still_emits_only_movie_event(self):
        self.invoke('SetCurrentSettingValue',10,65002,1)
        self.invoke('OnExitScreen')
        events=[a for n,a in self.calls if n=='SendSystemEvent']
        self.assertTrue(any('Server16MatchMovie' in a for a in events))
        self.assertFalse(any('Server16MatchScoreboard' in a for a in events))

    def test_reset_keeps_movie_and_attendance_contract(self):
        self.invoke('ResetGameSettings');self.invoke('OnExitScreen')
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,65001),0)
        self.assertEqual(self.invoke('GetCurrentSettingValue',10,65002),0)
        self.assertFalse(any(n=='SendSystemEvent' and 'Server16MatchScoreboard' in a for n,a in self.calls))

    def test_ui_integrity_and_movie_initial_offset(self):
        data,offset=options.verified_ui(self.root,self.record)
        self.assertEqual(offset,self.record['movie_initial_offset'])
        self.assertNotIn('initial_value_offset',self.record)
        self.assertNotIn(b'Server16MatchScoreboard',data)


class AssignmentPriority(unittest.TestCase):
    def setUp(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from server16_py.asset_runtime import AssetRuntime
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.rules={}
        for name in ['League','Stage','Exact','Home','Default','Brazil']:
            p=self.root/'ScoreBoardGBD'/name/'game/test.big';p.parent.mkdir(parents=True);p.write_bytes(name.encode())
        self.rules[('Scoreboard','0')]='Default'
        self.app=SimpleNamespace(exedir=self.root,ScoreBoard=self.root/'ScoreBoardGBD',TOURNAME='100',TOURROUNDID='102',HID='7',tvlogoscoreboardtype='default',settings_ini=SimpleNamespace(read=lambda k,s:self.rules.get((s,k),'')),log=lambda *a:None)
        self.runtime=AssetRuntime(self.app)
        patcher=patch('server16_py.competition_catalog.nodes',return_value={100:(3,'C1','League',9),101:(4,'S1','Stage',100),102:(5,'G1','Group',101),9:(2,'N','Nation',0)})
        patcher.start();self.addCleanup(patcher.stop)

    def test_group_inherits_stage_only_when_no_explicit_assignment(self):
        self.rules[('Scoreboard','101')]='Stage'
        self.assertEqual(self.runtime._scoreboard_package()[0],'Stage')

    def test_explicit_competition_can_use_any_package_over_parent_stage(self):
        self.rules.update({('Scoreboard','101'):'Stage',('Scoreboard','100'):'Brazil'})
        self.assertEqual(self.runtime._scoreboard_package()[0],'Brazil')

    def test_exact_round_priority_is_unchanged(self):
        self.rules.update({('Scoreboard','102'):'Exact',('Scoreboard','100'):'League',('HomeTeamScoreBoard','7'):'Home'})
        self.assertEqual(self.runtime._scoreboard_package()[0],'Exact')

    def test_home_team_priority_is_unchanged(self):
        self.rules.update({('Scoreboard','101'):'Stage',('HomeTeamScoreBoard','7'):'Home'})
        self.assertEqual(self.runtime._scoreboard_package()[0],'Home')

    def test_missing_package_falls_through_without_breaking_next_rule(self):
        self.rules.update({('Scoreboard','102'):'Missing',('Scoreboard','100'):'League'})
        self.assertEqual(self.runtime._scoreboard_package()[0],'League')

    def test_unknown_ids_keep_default_and_never_use_nation(self):
        self.app.TOURNAME='8000';self.app.TOURROUNDID='8001'
        self.assertEqual(self.runtime._scoreboard_package()[0],'Default')
