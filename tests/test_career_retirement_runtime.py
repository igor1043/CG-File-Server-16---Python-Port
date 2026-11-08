import importlib
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server16_py.career_retirement_runtime import RetirementRuntime,fields
MODULE='server16_py.career_retirement_runtime'

class LiveRetirementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=SimpleNamespace(base_dir=self.tmp.name,exedir=self.tmp.name,memory=SimpleNamespace(process_id=45))
        self.runtime=RetirementRuntime(self.app);self.runtime.root.mkdir(parents=True)
        self.profile=dict(career_role=1,context_epoch=8,context_address=0x1000,registry_address=0x2000,club_id=1043)
        self.ready=dict(schema=1,pid=45,created=12345,epoch=8,context='1000',registry='2000',club=1043,date=20261107,tick=10000)
        self.write('retirement_ready.tsv',self.ready)
        self.addCleanup(patch.stopall)
        patch(MODULE+'.process_created',return_value=12345).start()
        patch(MODULE+'.ticks',return_value=10001).start()
    def write(self,name,values):
        (self.runtime.root/name).write_text(''.join(f'{k}={v}\n' for k,v in values.items()),encoding='ascii')
    def request(self):return self.runtime.request(self.profile,False,18)
    def test_request_is_scoped_and_never_edits_or_queues_an_offline_save(self):
        ticket=self.request();parts=(self.runtime.root/'retirement_request.tsv').read_text().split()
        self.assertEqual(parts[:8],['1','45','12345','8','1000','2000','1043','20261107'])
        self.assertEqual(parts[8],ticket['id']);self.assertEqual(parts[9:11],['0','18'])
        self.assertFalse((self.runtime.root/'pending.json').exists())
    def test_rejects_stale_and_foreign_capabilities(self):
        for changes in (dict(pid=46),dict(created=12346),dict(epoch=7),dict(context='9999'),dict(registry='9999'),dict(club=1),dict(tick=1),dict(tick=10002)):
            with self.subTest(changes=changes):
                self.write('retirement_ready.tsv',dict(self.ready,**changes))
                with self.assertRaises(ValueError):self.request()
                self.assertFalse((self.runtime.root/'retirement_request.tsv').exists())
    def test_player_career_and_bad_age_are_rejected(self):
        with self.assertRaises(ValueError):self.runtime.request(dict(self.profile,career_role=2),False,18)
        for age in (True,11,51,'18'):
            with self.assertRaises(ValueError):self.runtime.request(self.profile,False,age)
    def response(self,ticket,**changes):
        self.write('retirement_response.tsv',dict(schema=1,id=ticket['id'],pid=45,created=12345,epoch=8,context='1000',club=1043,status=0,eligible=4,changed=4,**changes))
    def test_only_matching_native_ack_is_success_and_saving_stays_explicit(self):
        ticket=self.request();self.assertIsNone(self.runtime.poll(ticket,self.profile))
        self.response(ticket);result=self.runtime.poll(ticket,self.profile)
        self.assertEqual(result['players_changed'],4);self.assertTrue(result['native_save_pending'])
        self.write('retirement_response.tsv',dict(schema=1,id='0'*32))
        self.assertIsNone(self.runtime.poll(ticket,self.profile))
    def test_save_switch_is_not_replayed(self):
        ticket=self.request();raw=(self.runtime.root/'retirement_request.tsv').read_bytes()
        with self.assertRaises(ValueError):self.runtime.poll(ticket,dict(self.profile,context_epoch=9))
        self.assertEqual(raw,(self.runtime.root/'retirement_request.tsv').read_bytes())
    def test_failure_and_timeout_are_not_success_or_retries(self):
        ticket=self.request()
        self.write('retirement_response.tsv',dict(schema=1,id=ticket['id'],pid=45,created=12345,epoch=8,context='1000',club=1043,status=2,eligible=4,changed=0))
        with self.assertRaises(ValueError):self.runtime.poll(ticket,self.profile)
        self.write('retirement_response.tsv',dict(schema=1,id='0'*32));ticket['started']=time.monotonic()-21
        with self.assertRaises(ValueError):self.runtime.poll(ticket,self.profile)
    def test_duplicate_keys_are_invalid(self):
        path=self.runtime.root/'bad.tsv';path.write_text('schema=1\nschema=0\n')
        with self.assertRaises(ValueError):fields(path)

if __name__=='__main__':unittest.main()
