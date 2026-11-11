import tempfile,unittest,sys,os
from pathlib import Path
from unittest.mock import patch
from server16_py.club_environment import prepare_runtime,worker,atomic_copy,ENTRIES

class PortableRuntimeTest(unittest.TestCase):
    def test_source_code_wins_over_old_seed_on_every_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp);self.fixture(game)
            source=game/'ModCarrerMode/source/club_environment/room'/ENTRIES['room']
            seed=game/'ModCarrerMode/data/club_environment/room'/ENTRIES['room']
            seed.parent.mkdir(parents=True);seed.write_text('obsolete seed')
            for _ in range(3):
                _,runtime=prepare_runtime(game)
                self.assertEqual((runtime/'room'/ENTRIES['room']).read_bytes(),source.read_bytes())

    def test_copy_retries_windows_lock_without_truncating_target(self):
        import server16_py.club_environment as module
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'source.py';target=folder/'target.py'
            source.write_text('new helper');target.write_text('working old helper');replace=os.replace;calls=[]
            def locked(src,dst):
                calls.append(str(src));self.assertEqual(target.read_text(),'working old helper')
                if len(calls)<3:raise PermissionError(5,'Access denied')
                replace(src,dst)
            with patch.object(module.os,'replace',side_effect=locked),patch.object(module.time,'sleep') as pause:
                atomic_copy(source,target)
            self.assertEqual(target.read_text(),'new helper');self.assertEqual(pause.call_count,2)
            self.assertEqual(list(folder.glob('*.new')),[])

    def test_completed_concurrent_copy_is_accepted_and_temp_removed(self):
        import server16_py.club_environment as module
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'source.py';target=folder/'target.py';source.write_text('new helper')
            def other_writer(src,dst):target.write_bytes(source.read_bytes());raise PermissionError(5,'Access denied')
            with patch.object(module.os,'replace',side_effect=other_writer),patch.object(module.time,'sleep') as pause:
                atomic_copy(source,target)
            pause.assert_not_called();self.assertEqual(target.read_text(),'new helper');self.assertEqual(list(folder.glob('*.new')),[])

    def test_persistent_lock_is_bounded_and_keeps_old_target(self):
        import server16_py.club_environment as module
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'source.py';target=folder/'target.py';source.write_text('new');target.write_text('old')
            with patch.object(module.os,'replace',side_effect=PermissionError(5,'Access denied')) as replace,patch.object(module.time,'sleep'):
                with self.assertRaises(PermissionError):atomic_copy(source,target)
            self.assertEqual(replace.call_count,8);self.assertEqual(target.read_text(),'old');self.assertEqual(list(folder.glob('*.new')),[])

    def test_bootstrap_failure_is_logged_and_returns_failure_without_dialog(self):
        import server16_py.club_environment as module
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp)
            with patch.object(module,'prepare_runtime',side_effect=PermissionError(5,'locked helper')):
                self.assertEqual(worker(game,'room',123),1)
            log=game/'ModCarrerMode/runtime/club_environment/room/runtime/service.log'
            self.assertIn('PermissionError',log.read_text());self.assertIn('locked helper',log.read_text())

    def test_parallel_preparations_keep_one_current_runtime(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as temp:
            game=Path(temp);self.fixture(game)
            with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(prepare_runtime,[game]*8))
            for group,entry in ENTRIES.items():
                self.assertEqual((game/'ModCarrerMode/runtime/club_environment'/group/entry).read_bytes(),
                                 (game/'ModCarrerMode/source/club_environment'/group/entry).read_bytes())
            self.assertFalse(list(game.rglob('*.new')))

    @unittest.skipUnless(os.name=='nt','Windows sharing semantics')
    def test_real_windows_reader_lock_is_retried_then_installed(self):
        import ctypes,threading,time
        from ctypes import wintypes as W
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);source=folder/'source.py';target=folder/'target.py';source.write_text('new');target.write_text('old')
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,ctypes.c_void_p,W.DWORD,W.DWORD,W.HANDLE];kernel.CreateFileW.restype=W.HANDLE
            kernel.CloseHandle.argtypes=[W.HANDLE]
            handle=kernel.CreateFileW(str(target),0x80000000,3,None,3,0x80,None)
            self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            failures=[]
            def copy():
                try:atomic_copy(source,target)
                except Exception as error:failures.append(error)
            task=threading.Thread(target=copy);task.start()
            try:time.sleep(.15);self.assertEqual(target.read_text(),'old')
            finally:kernel.CloseHandle(handle)
            task.join(5);self.assertFalse(task.is_alive());self.assertEqual(failures,[])
            self.assertEqual(target.read_text(),'new');self.assertFalse(list(folder.glob('*.new')))
    def test_manager_market_worker_logs_in_its_own_runtime(self):
        with tempfile.TemporaryDirectory(prefix='FIFA manager bootstrap ') as temp:
            game=Path(temp);self.fixture(game)
            flags={'SERVER16_MANAGER_MARKET_WORKER':'1',
                   'SERVER16_CLUB_BROWSER_WORKER':'','SERVER16_TRANSFER_MARKET_WORKER':''}
            with patch.dict(os.environ,flags),patch.object(sys,'path',list(sys.path)),patch.object(sys,'argv',list(sys.argv)):
                worker(game,'preview',123)
            log=game/'ModCarrerMode/runtime/manager_market/bootstrap.log'
            self.assertIn('WORKER_START',log.read_text(encoding='utf8'))
            self.assertTrue((game/'ModCarrerMode/runtime/club_environment/preview/prepare.called').is_file())
            self.assertFalse((game/'ModCarrerMode/runtime/club_environment/preview/runtime/service.log').exists())

    def test_invalid_inherited_stdout_cannot_abort_the_worker(self):
        class BrokenStream:
            def write(self,*args):raise OSError(22,'Invalid argument')
            def flush(self):pass
        with tempfile.TemporaryDirectory(prefix='FIFA stdout ') as temp:
            game=Path(temp);self.fixture(game)
            entry=game/'ModCarrerMode/source/club_environment/preview/prepare.py'
            entry.write_text("print('REQUEST must reach the log',flush=True)\n"+entry.read_text(),encoding='utf8')
            with patch.dict(os.environ,{},clear=False),patch.object(sys,'path',list(sys.path)),patch.object(sys,'argv',list(sys.argv)),patch.object(sys,'stdout',BrokenStream()),patch.object(sys,'stderr',BrokenStream()):
                worker(game,'preview',123)
            runtime=game/'ModCarrerMode/runtime/club_environment/preview'
            self.assertTrue((runtime/'prepare.called').is_file())
            self.assertIn('REQUEST must reach the log',(runtime/'runtime/service.log').read_text(encoding='utf8'))
    def test_paths_with_spaces_and_loan_upgrade_preserves_private_ledger(self):
        with tempfile.TemporaryDirectory(prefix='FIFA portable ') as temp:
            game=Path(temp);source=game/'ModCarrerMode/source/club_environment'
            entries={'room':'prepare_native_room_components_r46_20261022.py','bank':'watch_r57.py','preview':'prepare.py'}
            for group,entry in entries.items():
                path=source/group/entry;path.parent.mkdir(parents=True);path.write_text('# helper')
            previous=game/'ModCarrerMode/experiments/career_bank_20261021/runtime'/('a'*20)
            previous.mkdir(parents=True);(previous/'pending.json').write_text('private ledger')
            s,r=prepare_runtime(game)
            self.assertEqual(s,source);self.assertEqual((r/'bank/runtime'/('a'*20)/'pending.json').read_text(),'private ledger')
            (r/'bank/runtime'/('a'*20)/'pending.json').write_text('newer ledger');prepare_runtime(game)
            self.assertEqual((r/'bank/runtime'/('a'*20)/'pending.json').read_text(),'newer ledger')
            self.assertFalse((source/'bank/pending.json').exists())

    def fixture(self,game):
        for group,entry in ENTRIES.items():
            path=game/'ModCarrerMode/source/club_environment'/group/entry
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text("from pathlib import Path\nimport sys\nPath(__file__).with_suffix('.called').write_text('|'.join(sys.argv[1:]),encoding='utf8')\n",encoding='utf8')

    def test_direct_worker_prepares_missing_runtime_before_entry(self):
        for kind,entry in ENTRIES.items():
            with self.subTest(kind=kind),tempfile.TemporaryDirectory(prefix='FIFA inicialização ') as temp:
                game=Path(temp);self.fixture(game)
                self.assertFalse((game/'ModCarrerMode/runtime/club_environment').exists())
                with patch.dict(os.environ,{},clear=False),patch.object(sys,'path',list(sys.path)),patch.object(sys,'argv',list(sys.argv)):
                    worker(game,kind,123)
                called=game/'ModCarrerMode/runtime/club_environment'/kind/Path(entry).with_suffix('.called')
                self.assertEqual(called.read_text(encoding='utf8'),'--watch|--pid|123')

    def test_direct_worker_recovers_deleted_entry_and_preserves_ledger(self):
        with tempfile.TemporaryDirectory(prefix='FIFA recover ') as temp:
            game=Path(temp);self.fixture(game);_,runtime=prepare_runtime(game)
            ledger=runtime/'bank/runtime/ledger.sqlite';ledger.write_bytes(b'private-contract')
            (runtime/'preview/prepare.py').unlink()
            with patch.dict(os.environ,{},clear=False),patch.object(sys,'path',list(sys.path)),patch.object(sys,'argv',list(sys.argv)):
                worker(game,'preview',123)
            self.assertTrue((runtime/'preview/prepare.called').exists())
            self.assertEqual(ledger.read_bytes(),b'private-contract')
