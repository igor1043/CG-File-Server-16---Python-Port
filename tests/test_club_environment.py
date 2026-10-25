import tempfile,unittest,sys,os
from pathlib import Path
from unittest.mock import patch
from server16_py.club_environment import prepare_runtime,worker,ENTRIES

class PortableRuntimeTest(unittest.TestCase):
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
