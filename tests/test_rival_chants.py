import os
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from server16_py.chants_runtime import ChantsRuntime
from server16_py.rival_chants import RivalChants


class RivalChantsTests(unittest.TestCase):
    def make_runtime(self, root):
        app=SimpleNamespace(exedir=root,HID='1',AID='2',_kickoff_generation=1,
                            _chants_rng=random.Random(5),log=Mock())
        return ChantsRuntime(app)

    def pack(self, root):
        support=root/'Support'; support.mkdir()
        normal=support/'normal.mp3'; normal.write_bytes(b'normal')
        special=support/'Rivals'/'2'; special.mkdir(parents=True)
        rival=special/'rival.mp3'; rival.write_bytes(b'rival')
        (special/'backup.original.mp3').write_bytes(b'backup')
        (special/'empty.mp3').touch()
        (special/'nested').mkdir(); (special/'nested'/'ignored.mp3').write_bytes(b'nested')
        return support,normal,rival

    def test_matching_opponent_only_and_no_recursive_normal_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self.make_runtime(Path(tmp)); support,normal,rival=self.pack(Path(tmp))
            runtime.app._chants_rng=Mock(random=Mock(return_value=0),choice=Mock(side_effect=lambda seq:seq[0]))
            self.assertEqual(runtime._pick_crowd_track(support,'2 extra'),rival)
            self.assertEqual(runtime._pick_crowd_track(support,'3'),normal)
            self.assertEqual(runtime._pick_random_track(support),normal)
            for invalid in ('../2','2/3','-2','',None,'２'):
                self.assertEqual(runtime._pick_crowd_track(support,invalid),normal)

    def test_complaint_unchanged_and_missing_folder_does_not_consume_rng(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); runtime=self.make_runtime(root); support,normal,rival=self.pack(root)
            complaint=root/'Complaint'; complaint.mkdir(); track=complaint/'complaint.mp3'; track.touch()
            rng=Mock(random=Mock(return_value=0),choice=Mock(side_effect=lambda seq:seq[0]))
            runtime.app._chants_rng=rng
            self.assertEqual(runtime._pick_crowd_track(complaint,'2'),track)
            self.assertEqual(runtime._pick_crowd_track(support,'3'),normal)
            rng.random.assert_not_called()

    def test_weight_is_pool_based_not_file_count_and_no_immediate_rival_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self.make_runtime(Path(tmp)); support,normal,rival=self.pack(Path(tmp))
            rng=Mock(random=Mock(return_value=.25),choice=Mock(side_effect=lambda seq:seq[0]))
            runtime.app._chants_rng=rng
            self.assertEqual(runtime._pick_crowd_track(support,'2'),normal)
            rng.random.return_value=.249
            self.assertEqual(runtime._pick_crowd_track(support,'2'),rival)
            self.assertEqual(runtime._pick_crowd_track(support,'2',rival),normal)

    def test_bad_special_falls_back_using_same_player_and_is_excluded_for_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self.make_runtime(Path(tmp)); support,normal,rival=self.pack(Path(tmp))
            runtime.app._chants_rng=Mock(random=Mock(return_value=0),choice=Mock(side_effect=lambda seq:seq[0]))
            runtime._pick_crowd_track(support,'2')
            player=Mock(); player.open.side_effect=[RuntimeError('bad mp3'),None]
            self.assertEqual(runtime._open_crowd_track(player,rival,support),normal)
            self.assertEqual(player.open.call_count,2)
            self.assertEqual(runtime._pick_crowd_track(support,'2'),normal)
            runtime.app._kickoff_generation+=1
            self.assertEqual(runtime._pick_crowd_track(support,'2'),rival)

    def test_reverse_fixture_resolves_other_crowd_and_updates_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self.make_runtime(Path(tmp)); support,normal,rival=self.pack(Path(tmp))
            pool=RivalChants(runtime.app)
            self.assertEqual(pool.tracks(support,'2'),(rival,))
            self.assertEqual(pool.tracks(support,'1'),())
            runtime.app.HID,runtime.app.AID='2','1'
            self.assertEqual(pool.tracks(support,'2'),(rival,))
            stamp=rival.parent.stat().st_mtime_ns
            extra=rival.with_name('other.mp3'); extra.write_bytes(b'other')
            # Rapid writes can share a directory timestamp on Windows. Make the
            # external directory update explicit instead of relying on timing.
            os.utime(rival.parent,ns=(stamp+1000000000,stamp+1000000000))
            self.assertEqual(set(pool.tracks(support,'2')),{rival,extra})

    def test_play_failure_falls_back_and_away_normal_selection_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=self.make_runtime(Path(tmp)); support,normal,rival=self.pack(Path(tmp))
            runtime.app._chants_rng=Mock(random=Mock(return_value=0),choice=Mock(side_effect=lambda seq:seq[0]))
            runtime._pick_crowd_track(support,'2')
            player=Mock(); player.play.side_effect=[RuntimeError('bad stream'),None]
            self.assertEqual(runtime._open_crowd_track(player,rival,support),normal)
            self.assertEqual(player.play.call_count,2)
            self.assertEqual(runtime._pick_crowd_track(support,'3',normal,avoid_normal_repeat=False),normal)
