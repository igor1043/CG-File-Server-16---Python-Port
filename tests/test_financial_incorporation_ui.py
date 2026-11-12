from pathlib import Path
import os,tempfile,unittest
from server16_py import financial_incorporation_ui as screen
from formats import BigFile,AptFile
from apt_actions import Actions
from apt_vm import Object,Native
from apt_test_vm import NativeVM

class SetupVM(NativeVM):
    def get(self,obj,key):
        if isinstance(obj,list) and key=='pop':return Native('pop')
        return super().get(obj,key)
    def invoke(self,function,owner,args=()):
        if self.depth==0:self.steps=0
        if isinstance(function,Native) and function.name=='pop':return owner.pop()
        return super().invoke(function,owner,args)

class FinancialSetup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();original=Path(os.environ['CAREER_SETUP_ORIGINAL']);cls.output=Path(cls.temp.name)/'setup.big'
        screen.build(Path(os.environ['SERVER16_GAME_ROOT']),original,cls.output)
        before=AptFile(BigFile(original));after=AptFile(BigFile(cls.output));cls.original=before;cls.apt=after
        registration=lambda apt:next(c for c in apt.root_frames[0] if isinstance(c,tuple) and c[0]=='init' and c[1]==apt.exports['__Packages.'+screen.FULL])
        old=Actions(before).read_all().cache[registration(before)[-1]]
        actions=Actions(after).read_all();assert not actions.errors,actions.errors
        cls.code=actions.cache[registration(after)[-1]][len(old)-1:]
        a,b=BigFile(original),BigFile(cls.output)
        cls.changed_entries=[name for name in a.entries if bytes(a.entries[name].data)!=bytes(b.entries[name].data)]
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.calls=[];self.index=0;self.rows=[Object(dict(NAME='advance',TYPE='BUTTON'))]+[Object(dict(NAME=name,TYPE='TOGGLE')) for name in ('difficulty','half','strictness','currency','stadium','squads','window')]
        self.control=Object({name:Object(dict(_visible=True)) for name in ('txtButton','txtLabel','txtLink','mcCheckMark')})
        self.control.set('mcToggle',Object(dict(setIndexByValue=Native('setIndexByValue'))))
        def callback(name,owner,args):
            self.calls.append((name,args))
            if name=='baseInit':owner.set('m_RowData',self.rows.copy());owner.set('m_TogglesData',Object())
            if name=='baseRows':self.assertEqual(owner.get('m_RowData'),self.rows)
            if name=='getRowAtIndex':return self.control
            if name=='getSelectedIndex':return self.index
            if name=='baseInput':return 'original-result'
        self.vm=SetupVM(callback)
        proto=Object({method:Native(name) for method,name in [('_InitComponentsData','baseInit'),('_InitRowControlData','baseRows'),('_LocalEventHandler','baseInput'),('_OnExitScreen','baseExit'),('_OnAnimateInComplete','baseComplete')]})
        self.klass=Object(dict(prototype=proto,TYPE_TOGGLE='TOGGLE'))
        self.vm.global_.set('game',Object(dict(screens=Object(dict(career=Object(dict(Setup=self.klass)))))))
        self.codes=dict(BACK=1,ADVANCE=2,UI_UP=3,UI_DOWN=4,UI_LEFT=5,UI_RIGHT=6)
        self.vm.global_.set('INPUTCODE',Object(self.codes));self.vm.global_.set('ION_CareerMode',Object(dict(SendSystemEvent=Native('SendSystemEvent'))))
        self.vm.run(self.code,self.vm.global_,self.vm.global_)
        self.view=Object(dict(mcRowControl=Object(dict(getRowAtIndex=Native('getRowAtIndex'),getSelectedIndex=Native('getSelectedIndex'))),_PopulateToggle=Native('populate'),_UpdateRow=Native('update')),proto)
        self.invoke('_InitComponentsData');self.invoke('_InitRowControlData');self.invoke('_OnAnimateInComplete')
    def invoke(self,name,*args):return self.vm.invoke(self.view.get(name),self.view,args)
    def press(self,key):return self.invoke('_LocalEventHandler',self.codes[key],'keyboard')
    def commands(self):return [args[-1] for name,args in self.calls if name=='SendSystemEvent']
    def test_keeps_all_native_rows_art_and_provider_requests(self):
        self.assertEqual(self.original.exports,self.apt.exports);self.assertEqual(len(self.changed_entries),1)
        rows=self.view.get('m_RowData');self.assertEqual(rows[:-1],self.rows)
        # The inspection decoder retains bytes as Latin-1; FIFA renders UTF-8.
        self.assertEqual(rows[-1].get('LABEL').encode('latin1').decode('utf8'),'Incorporação Financeira')
        self.assertEqual(self.view.get('S16FinancialRow'),8)
        values=self.view.get('m_TogglesData').get(8);self.assertEqual(len(values),len(screen.AMOUNTS))
        self.assertEqual(values[0].get('TEXT'),'Desativado')
        self.assertFalse(self.control.get('txtButton').get('_visible'));self.assertFalse(self.control.get('txtLink').get('_visible'))
        self.assertTrue(self.control.get('mcToggle').get('_visible'));self.assertTrue(self.control.get('txtLabel').get('_visible'))
        self.assertEqual(self.commands(),['S16FUND1|BEGIN|0|END'])
    def test_left_right_wraps_without_changing_any_native_option(self):
        self.index=8;self.press('UI_LEFT');self.assertEqual(self.view.get('S16FinancialIndex'),len(screen.AMOUNTS)-1)
        self.press('UI_RIGHT');self.assertEqual(self.view.get('S16FinancialIndex'),0)
        self.press('UI_RIGHT');self.assertEqual(self.view.get('S16FinancialIndex'),1)
        self.assertFalse(any(name=='baseInput' for name,args in self.calls))
        self.assertEqual(self.commands(),['S16FUND1|BEGIN|0|END'])
    def test_only_advance_on_original_first_row_arms_the_new_career(self):
        self.index=8;self.press('UI_RIGHT');self.press('ADVANCE');self.assertEqual(len(self.commands()),1)
        self.index=0;self.assertEqual(self.press('ADVANCE'),'original-result')
        self.assertEqual(self.commands()[-1],'S16FUND1|ARM|10000|END')
        self.invoke('_OnExitScreen');self.assertNotIn('S16FUND1|CANCEL|0|END',self.commands())
    def test_back_or_unconfirmed_exit_cancels_and_native_navigation_survives(self):
        self.index=4;self.assertEqual(self.press('UI_RIGHT'),'original-result');self.press('BACK')
        self.assertEqual(self.commands()[-1],'S16FUND1|CANCEL|0|END')
        self.invoke('_OnExitScreen');self.assertEqual(self.calls[-1][0],'baseExit')
    def test_new_view_resets_to_disabled(self):
        self.index=8;self.press('UI_RIGHT');self.invoke('_InitComponentsData')
        self.assertEqual(self.view.get('S16FinancialIndex'),0)
    def test_200_and_500_million_are_real_advance_requests(self):
        for amount in (200000000,500000000):
            self.invoke('_InitComponentsData');self.invoke('_InitRowControlData')
            self.index=8
            for _ in range(screen.AMOUNTS.index(amount)):self.press('UI_RIGHT')
            self.index=0;self.press('ADVANCE')
            self.assertEqual(self.commands()[-1],f'S16FUND1|ARM|{amount}|END')
    def test_upgrading_own_screen_keeps_native_base_methods_and_all_choices(self):
        rebuilt=Path(self.temp.name)/'upgrade.big'
        screen.build(Path(os.environ['SERVER16_GAME_ROOT']),self.output,rebuilt)
        apt=AptFile(BigFile(rebuilt));actions=Actions(apt).read_all()
        self.assertFalse(actions.errors)
        registration=next(c for c in apt.root_frames[0] if isinstance(c,tuple) and c[0]=='init' and c[1]==apt.exports['__Packages.'+screen.FULL])
        code=actions.cache[registration[-1]]
        self.assertEqual(sum(row.value=='S16FinancialInstalled' for row in code if isinstance(row.value,str)),2)

if __name__=='__main__':unittest.main()
