from pathlib import Path
import json, os, shutil, sqlite3, tempfile, time, unittest
from unittest.mock import patch
from server16_py import cache_maintenance as cache
from server16_py import session_storage as storage

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.game=self.root/'game'
        for relative in ('ModCarrerMode/data','data/sceneassets','runtime'):
            (self.game/relative).mkdir(parents=True,exist_ok=True)

    def file(self,path,body=b'temporary'):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(body)
        os.utime(path,(1,1))
        return path

    def bundle(self,name,owned=True):
        folder=self.root/name
        self.file(folder/'payload.bin',b'x'*8)
        if owned:
            for marker in storage.LEGACY_MARKERS:self.file(folder/marker)
        os.utime(folder,(1,1))
        return folder

    def sweep(self,**kwargs):
        return storage.sweep_extractions(roots=[(self.root,False)],grace=0,snapshot=lambda:(set(),{}),**kwargs)

    def test_legacy_ownership_and_ended_bundle_only(self):
        old=self.bundle('_MEI7654321')
        other=self.bundle('_MEI7654322',False)
        unknown=self.bundle('Server16_UserData')
        result=self.sweep()
        self.assertFalse(old.exists())
        self.assertTrue(other.exists() and unknown.exists())
        self.assertEqual(1,result.removed)
        self.assertGreater(result.released_bytes,0)

    def test_live_child_environment_pins_bundle(self):
        folder=self.bundle('_MEI7654321')
        result=storage.sweep_extractions(roots=[(self.root,False)],grace=0,
                                        snapshot=lambda:({folder.resolve()},{}))
        self.assertTrue(folder.exists())
        self.assertEqual(0,result.removed)
        self.assertGreater(result.retained_bytes,0)

    def test_pid_prefix_pins_even_during_loader_startup(self):
        folder=self.bundle('_MEI7654321')
        born=getattr(folder.stat(),'st_birthtime',folder.stat().st_ctime)
        result=storage.sweep_extractions(roots=[(self.root,False)],grace=5,
                                        snapshot=lambda:(set(),{'76543':born}))
        self.assertTrue(folder.exists())
        self.assertEqual(0,result.removed)

    def test_recent_unknown_or_linked_payload_is_never_removed(self):
        folder=self.bundle('_MEI7654321')
        os.utime(folder,None)
        result=storage.sweep_extractions(roots=[(self.root,False)],grace=120,snapshot=lambda:(set(),{}))
        self.assertTrue(folder.exists())
        self.assertEqual(0,result.removed)

    def test_dry_run_does_not_remove_a_bundle(self):
        folder=self.bundle('_MEI7654321')
        report=self.sweep(dry_run=True)
        self.assertTrue(folder.exists())
        self.assertEqual(1,report.removed)

    def test_access_failure_aborts_the_sweep(self):
        folder=self.bundle('_MEI7654321')
        import psutil
        def denied():raise psutil.AccessDenied(1)
        report=storage.sweep_extractions(roots=[(self.root,False)],grace=0,snapshot=denied)
        self.assertTrue(folder.exists())
        self.assertEqual(1,report.skipped)

    def calendar(self):
        return self.game/'ModCarrerMode/runtime/manager_market/league_days/123-134385271912386776-2-99765870'

    def test_only_exact_closed_calendar_names_are_candidates(self):
        folder=self.calendar()
        old=self.file(folder/'20260101.campaign.json')
        valid=self.file(folder/'20260102.tsv')
        sql=self.file(folder/'history.sqlite3')
        bad=self.file(folder/'20260230.tsv')
        nested=self.file(folder/'assets/20260101.tsv')
        with patch.object(storage,'_pending_save_owners',return_value=set()):
            found=set(storage.finished_calendar_files(self.game,alive=lambda pid:False))
        self.assertEqual({old,valid},found)
        self.assertTrue(all(p.exists() for p in (sql,bad,nested)))

    def test_live_and_pending_owners_pin_every_calendar_file(self):
        path=self.file(self.calendar()/'20260101.campaign.json')
        owner=(123,134385271912386776)
        with patch.object(storage,'_pending_save_owners',return_value={owner}):
            self.assertEqual([],list(storage.finished_calendar_files(self.game,alive=lambda pid:False)))
        with patch.object(storage,'_pending_save_owners',return_value=set()):
            self.assertEqual([],list(storage.finished_calendar_files(self.game,alive=lambda pid:True)))
        self.assertTrue(path.exists())

    def test_native_receipt_pins_until_sql_binding(self):
        saved=self.root/'save/DATA'
        header=bytearray(160)
        header[116:132]=b'SaveType_Career\0'
        header[132:136]=(27).to_bytes(4,'little')
        self.file(saved,header)
        receipt=self.file(self.game/'ModCarrerMode/runtime/manager_market/save_events/e1.tsv',
                          ('operation=write\ncomplete_file=1\nsave_type=SaveType_Career\n'
                           'pid=123\nprocess_created_100ns=134385271912386776\n'
                           'size_bytes=160\npayload_crc32=27\npath='+str(saved)+'\n').encode())
        db=sqlite3.connect(saved.with_name('server16_manager_market.sqlite3'))
        self.addCleanup(db.close)
        db.execute('CREATE TABLE save_receipts(event_id TEXT,pid INT,created INT)')
        db.commit()
        self.assertEqual({(123,134385271912386776)},storage._pending_save_owners(self.game))
        db.execute('INSERT INTO save_receipts VALUES(?,?,?)',('e1',123,134385271912386776))
        db.commit()
        self.assertEqual(set(),storage._pending_save_owners(self.game))
        self.assertTrue(receipt.exists())
        self.assertEqual(bytes(header),saved.read_bytes())

    def test_commit_preserves_current_day_and_replaced_versions(self):
        folder=self.calendar()
        old=self.file(folder/'20260101.campaign.json')
        changed=self.file(folder/'20260102.campaign.json')
        current=self.file(folder/'20260103.campaign.json')
        entries={(int(p.name[:8]),p):(p.stat().st_mtime_ns,p.stat().st_size)
                 for p in (old,changed,current)}
        changed.write_bytes(b'new version published by FIFA')
        storage.prune_committed_calendar(self.game,entries,20260103)
        self.assertFalse(old.exists())
        self.assertTrue(changed.exists() and current.exists())
        self.assertEqual({(20260103,current)},set(entries))

    def test_cleanup_is_idempotent_and_preserves_save_sidecars(self):
        path=self.file(self.calendar()/'20260101.tsv')
        saved=self.file(self.game/'ModCarrerMode/runtime/manager_market/save_events/r.tsv',b'receipt')
        sql=self.file(self.game/'ModCarrerMode/runtime/manager_market/private.sqlite3',b'durable')
        with patch.object(storage,'_pending_save_owners',return_value=set()),patch.object(storage.psutil,'pid_exists',return_value=False):
            first=cache.maintain(self.game,guard=lambda:False,record=False,journals_only=True)
            second=cache.maintain(self.game,guard=lambda:False,record=False,journals_only=True)
        self.assertFalse(path.exists())
        self.assertEqual(1,first.files)
        self.assertEqual(0,second.files)
        self.assertEqual(b'receipt',saved.read_bytes())
        self.assertEqual(b'durable',sql.read_bytes())




class ChildOwnerTests(unittest.TestCase):
    def test_python_and_native_helpers_keep_their_loaded_bundle(self):
        from types import SimpleNamespace
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from server16_py import session_storage as storage
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory)/'_MEI43121'
            parent.mkdir()
            python=SimpleNamespace(info=dict(pid=6,name='python.exe',create_time=1,exe='C:/Python/python.exe'),
                                   environ=lambda:{'_PYI_APPLICATION_HOME_DIR':str(parent)})
            native=SimpleNamespace(info=dict(pid=7,name='helper.exe',create_time=2,exe=str(parent/'bin/helper.exe')))
            with patch.object(storage.psutil,'process_iter',return_value=[python,native]):
                used,births=storage._process_snapshot()
            self.assertEqual({parent.resolve()},used)
            self.assertEqual({'6':1,'7':2},births)


if __name__=='__main__':unittest.main()
