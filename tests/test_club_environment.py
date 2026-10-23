import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from server16_py.club_environment import prepare_runtime

class PortableRuntimeTest(unittest.TestCase):
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
