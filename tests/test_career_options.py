from pathlib import Path
import sqlite3,tempfile,unittest
from contextlib import closing
from server16_py.career_options import chance,decide,add_days,native_path,CareerOptions
from types import SimpleNamespace
from unittest.mock import patch


class CareerOptionsPolicyTest(unittest.TestCase):
 def setUp(self):self.db=sqlite3.connect(':memory:');self.low=dict(id=1,reputation=3,level=3);self.high=dict(id=2,reputation=9,level=1)
 def tearDown(self):self.db.close()
 def test_prestige_and_division_set_the_probability(self):
  self.assertLessEqual(chance(self.low,self.high),30);self.assertGreater(chance(self.high,self.low),75)
  self.assertEqual(55,chance(self.low,self.low));self.assertLess(chance(dict(self.low,level=4),self.high),chance(self.low,self.high))
 def test_rejection_blocks_all_destinations_and_survives_reopen(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'ledger.sqlite3'
   with closing(sqlite3.connect(path)) as db,db:result=decide(db,'career-A','one',20260120,self.low,self.high,lambda n:n-1)
   self.assertFalse(result['accepted']);self.assertEqual(20260219,result['next_date'])
   with closing(sqlite3.connect(path)) as db,db:
    with self.assertRaises(ValueError):decide(db,'career-A','two',20260121,self.low,dict(self.high,id=3),lambda n:0)
    self.assertTrue(decide(db,'career-A','two',20260219,self.low,self.high,lambda n:0)['accepted'])
 def test_one_draw_idempotent_and_other_career_is_independent(self):
  result=decide(self.db,'A','request',20260101,self.low,self.high,lambda n:99 if n==100 else 0)
  repeated=decide(self.db,'A','request',20260101,self.low,self.high,lambda n:self.fail('duplicate drew again'))
  self.assertEqual(result['accepted'],repeated['accepted']);self.assertTrue(repeated['duplicate']);self.assertEqual(20260116,result['next_date'])
  self.assertTrue(decide(self.db,'B','request',20260101,self.low,self.high,lambda n:0)['accepted'])
 def test_month_and_leap_year_rollover(self):self.assertEqual(20240301,add_days(20240215,15));self.assertEqual(20270115,add_days(20261231,15))
 def test_native_path_diagnostic_escaping(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'DATA';p.touch();self.assertEqual(p.resolve(),native_path(str(p).replace('\\','\\\\')))

class CareerOptionsBridgeTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.calls=[];self.notices=[]
  data=dict(nations={'54':'Brasil'},leagues=[dict(id=1,country_id=54,level=3,name='Série C'),dict(id=2,country_id=54,level=1,name='Série A')],teams=[dict(id=1,name='Origem'),dict(id=2,name='Destino')],links=[(1,1),(2,2)])
  self.context=dict(userid=42,club_id=1,player_id=None);self.service=SimpleNamespace(app=SimpleNamespace(exedir=self.root,base_dir=self.root),selected=dict(path=str(self.root/'DATA')),inspection=dict(context=self.context,catalog=data),catalog=data,live_page=lambda:'game/screens/career/server16/CareerClubTransfer',in_career=lambda page:True,pending=None,busy=False,message='',require_active=lambda **kw:None,jobs_runtime=SimpleNamespace(ensure=lambda:None,ready=lambda:True),confirm=lambda *a,**kw:self.calls.append((a,kw)),notify=lambda *a:self.notices.append(a))
  self.bridge=CareerOptions(self.service);self.bridge.current=lambda:(self.context,{},7,1,20260101,'career-A');self.bridge.tick()
 def tearDown(self):self.tmp.cleanup()
 def request(self,action,token=None):
  (self.bridge.root/'request.tsv').write_text('\t'.join([token or self.bridge.token,'one',action,'2','2'])+'\n',encoding='utf8');self.bridge.next_tick=0;self.bridge.tick()
 def test_stale_request_never_reaches_the_existing_service(self):
  self.request('transfer','expired');self.assertFalse(self.calls);self.assertIn('expirado',self.bridge.message)
 def test_explicit_retirement_confirmation_reuses_existing_guarded_service(self):
  self.assertFalse(self.calls)
  with patch('server16_py.career_options.require_saved_day') as guard:self.request('remove_and_rejuvenate');guard.assert_called_once_with(self.service,20260101)
  self.assertEqual([(('remove_and_rejuvenate',),{})],self.calls)
 def test_older_save_blocks_retirement_without_enqueuing_an_edit(self):
  with patch('server16_py.career_options.require_saved_day',side_effect=ValueError('Salve a carreira antes de confirmar')):self.request('remove_retirement')
  self.assertFalse(self.calls);self.assertIn('Salve a carreira',self.bridge.message)
 def test_rejected_transfer_does_not_open_a_native_offer_and_blocks_new_club_request(self):
  with patch('server16_py.career_options.secrets.randbelow',side_effect=lambda n:n-1):self.request('transfer')
  self.assertFalse(self.calls);self.assertEqual(20260131,self.bridge.next_date);self.assertIn('recusou',self.bridge.message)
  with patch('server16_py.career_options.secrets.randbelow',side_effect=AssertionError('cooldown must not draw')):
   (self.bridge.root/'request.tsv').write_text('\t'.join([self.bridge.token,'two','transfer','2','2']),encoding='utf8');self.bridge.next_tick=0;self.bridge.tick()
  self.assertFalse(self.calls);self.assertIn('Aguarde',self.bridge.message)
 def test_accepted_transfer_uses_native_proposal_flow(self):
  with patch('server16_py.career_options.secrets.randbelow',return_value=0):self.request('transfer')
  self.assertEqual([(('transfer',),dict(team_id=2,league_id=2))],self.calls)

if __name__=='__main__':unittest.main()
