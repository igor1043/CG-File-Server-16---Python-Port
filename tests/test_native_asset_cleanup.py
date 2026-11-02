"""No file restoration during replays; atomic, background preparation for hubs."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import tempfile,unittest,threading,time
from server16_py.native_asset_cleanup import NativeAssetCleanup,idle_asset_page
from server16_py.app import Server16App


class NativeCleanupTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.app=SimpleNamespace(exedir=self.root,log=Mock(),lastpagename='game/screens/postGameFlow/MatchResults',
            _closing=False,_stadium_task_running=False,_match_audio_ended=True,_stadium_fixture_entered=True,_kickoff_generation=1)
        self.worker=NativeAssetCleanup(self.app);self.addCleanup(self.worker.close)

    def file(self,path,data):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p

    def hub(self):
        self.app.lastpagename='game/screens/fluxHub/FluxHub'
        self.worker.pulse();self.assertIsNotNone(self.worker.future)
        self.worker.future.result(timeout=20)

    def test_request_does_not_touch_results_highlights_penalties_replays_or_blank_loading(self):
        with patch('server16_py.native_asset_cleanup.prepare_restore') as prepare:
            self.worker.request()
            for page in ('game/screens/postGameFlow/MatchResults','game/screens/postGameFlow/MatchHighlights',
                         'game/screens/postGameFlow/PenaltyKickSelect','game/screens/instantReplay/ReplayScreen',''):
                self.app.lastpagename=page;self.worker.pulse()
            prepare.assert_not_called();self.assertTrue(self.worker.pending)

    def test_slow_disk_preparation_does_not_block_the_menu_poll(self):
        entered=threading.Event();release=threading.Event()
        from server16_py.native_asset_cleanup import prepare_restore
        def slow(app):
            entered.set();release.wait(10);return prepare_restore(app)
        with patch('server16_py.native_asset_cleanup.prepare_restore',side_effect=slow):
            try:
                self.worker.request();self.app.lastpagename='game/screens/fluxHub/FluxHub'
                began=time.monotonic();self.worker.pulse()
                self.assertLess(time.monotonic()-began,.5);self.assertTrue(entered.wait(2))
                self.assertFalse(self.worker.future.done())
            finally:release.set()
            self.worker.future.result(timeout=20)

    def test_stage_does_not_change_game_and_native_publication_preserves_immutable_resources(self):
        native=self.file('FSW/stadium/stadium/stadium_176.rx3',b'Native model')
        live=self.file('data/sceneassets/stadium/stadium_176.rx3',b'Server model')
        self.file('data/sceneassets/server16_match/abc/model.rx3',b'Immutable live model')
        route=self.file('data/fifarna/lua/assets/server16_match_176.lua',b'old fixture route')
        self.worker.request();self.hub()
        self.assertEqual(live.read_bytes(),b'Server model');self.assertEqual(route.read_bytes(),b'old fixture route')
        self.assertTrue(self.worker.pulse());self.assertEqual(live.read_bytes(),native.read_bytes())
        self.assertIn(b'[176] = nil',route.read_bytes())
        self.assertEqual((self.root/'data/sceneassets/server16_match/abc/model.rx3').read_bytes(),b'Immutable live model')
        self.assertTrue(self.app._stadium_assets_native)

    def test_loading_before_publication_discards_staging_without_late_file_changes(self):
        self.file('FSW/stadium/stadium/stadium_176.rx3',b'Native model')
        live=self.file('data/sceneassets/stadium/stadium_176.rx3',b'Server model')
        self.worker.request();self.hub();self.app.lastpagename='game/screens/TV/bumper'
        self.assertFalse(self.worker.pulse());self.assertTrue(self.worker.pending)
        self.assertEqual(live.read_bytes(),b'Server model')

    def test_generation_change_does_not_publish_a_plan_from_previous_fixture(self):
        self.file('FSW/ScoreBoard/test.big',b'Native scoreboard')
        live=self.file('data/ui/game/test.big',b'Competition scoreboard')
        self.worker.request();self.hub();self.app._kickoff_generation+=1
        self.assertFalse(self.worker.pulse());self.assertEqual(live.read_bytes(),b'Competition scoreboard')

    def test_unchanged_assets_are_not_staged_and_permission_repair_is_not_repeated(self):
        self.file('FSW/stadium/stadium/stadium_176.rx3',b'Native model')
        import shutil
        target=self.root/'data/sceneassets/stadium/stadium_176.rx3';target.parent.mkdir(parents=True)
        shutil.copy2(self.root/'FSW/stadium/stadium/stadium_176.rx3',target)
        self.worker.request()
        with patch('server16_py.file_tools.ensure_server16_stadium_access') as acl:
            self.hub();transaction,_=self.worker.future.result()
            self.assertFalse(list(transaction.stage.rglob('*.rx3')))
            self.worker.pulse();acl.assert_not_called()

    def test_auto_runtime_waits_for_restore_and_pause_is_not_idle_without_match_end(self):
        self.app._native_asset_cleanup=self.worker;self.worker.request()
        self.assertFalse(Server16App._should_auto_apply_runtime(self.app,'game/screens/playNow/KickOffHub'))
        self.app._match_audio_ended=False;self.app.lastpagename='game/screens/fluxHub/FluxHub'
        self.assertFalse(idle_asset_page(self.app))
        self.worker.pending=False
        self.assertTrue(Server16App._should_auto_apply_runtime(self.app,'game/screens/playNow/KickOffHub'))

    def test_manual_stadium_cannot_overtake_a_pending_native_restoration(self):
        from server16_py.stadium_runtime import StadiumRuntime
        self.app._native_asset_cleanup=self.worker;self.worker.request()
        runtime=StadiumRuntime(self.app)
        with patch.object(runtime,'_resolve_stadium_source') as source:
            with self.assertRaisesRegex(RuntimeError,'partida anterior'):runtime.apply_manual_stadium('A',())
            source.assert_not_called()

    def test_return_to_native_stadium_does_not_copy_or_change_injection_id_on_ui_thread(self):
        from server16_py.stadium_runtime import StadiumRuntime
        self.app.lastpagename='game/screens/playNow/KickOffHub';self.app._stadium_fixture_entered=False
        self.app.HID='1';self.app.AID='2';self.app._manual_stadium_override=None
        self.app.settings_ini=SimpleNamespace(key_exists=lambda *a:False)
        self.app.TOURROUNDID='0';self.app.TOURNAME='0';self.app._stadium_assets_native=False
        for name in ('_hide_stadium_loading_modal','_set_progress','_restore_native_runtime_assets'):setattr(self.app,name,Mock())
        self.app.memory=Mock();runtime=StadiumRuntime(self.app)
        with patch('server16_py.stadium_runtime.copy') as copy:
            runtime.apply_stadium_runtime();copy.assert_not_called()
        self.app._restore_native_runtime_assets.assert_called_once();self.app.memory.write_int.assert_not_called()


if __name__=='__main__':unittest.main()
