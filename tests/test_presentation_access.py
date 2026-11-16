"""Portable presentation copies and independent match modules, without UAC."""
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py import file_tools
from server16_py.asset_runtime import AssetRuntime
from server16_py.app import Server16App
from server16_py.memory_access import MemoryAccessError
from server16_py.offsets import Offsets
from server16_py.stadium_transaction import StadiumAssetTransaction


class PresentationAccessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def put(self, rel, data=b'new scoreboard'):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_readonly_source_and_destination_are_replaced_without_elevation(self):
        src = self.put('pack/game/score.big', b'complete replacement')
        dst = self.put('game/score.big', b'previous')
        src.chmod(stat.S_IREAD)
        dst.chmod(stat.S_IREAD)
        self.addCleanup(lambda: src.chmod(stat.S_IWRITE))
        with patch.object(file_tools.subprocess, 'run', side_effect=AssertionError('no permission tools')):
            self.assertTrue(file_tools._copy_file_if_needed(src, dst))
        self.assertEqual(dst.read_bytes(), src.read_bytes())
        self.assertFalse(dst.stat().st_file_attributes & 1)
        self.assertTrue(src.stat().st_file_attributes & 1)
        self.assertEqual(list(dst.parent.glob('.server16-*')), [])

    def test_interrupted_copy_preserves_previous_asset_and_removes_staging(self):
        src, dst = self.put('pack/source.big'), self.put('game/score.big', b'working')
        def interrupted(source, target):
            Path(target).write_bytes(b'half')
            raise OSError('disk unavailable')
        with patch.object(file_tools.shutil, 'copy2', side_effect=interrupted):
            with self.assertRaises(OSError): file_tools._copy_file_if_needed(src, dst)
        self.assertEqual(dst.read_bytes(), b'working')
        self.assertEqual(list(dst.parent.glob('.server16-*')), [])

    def test_real_access_denial_is_reported_without_elevation_or_losing_original(self):
        src, dst = self.put('pack/source.big'), self.put('game/score.big', b'working')
        with patch.object(file_tools.os, 'replace', side_effect=PermissionError('ACL denied')), patch.object(file_tools.subprocess, 'run') as run:
            with self.assertRaisesRegex(PermissionError, 'score.big'):
                file_tools._copy_file_if_needed(src, dst)
            run.assert_not_called()
        self.assertEqual(dst.read_bytes(), b'working')
        self.assertEqual(list(dst.parent.glob('.server16-*')), [])

    def test_access_check_does_not_require_write_dac_or_change_acl(self):
        with patch.object(file_tools.subprocess, 'run', side_effect=AssertionError('no ACL changes')):
            self.assertTrue(file_tools.ensure_server16_asset_access(self.root))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_stadium_rollback_retains_original_after_readonly_publication(self):
        rel = Path('data/sceneassets/stadium/stadium_176.rx3')
        original = self.put(rel, b'working model')
        original.chmod(stat.S_IREAD)
        self.addCleanup(lambda: original.chmod(stat.S_IWRITE))
        tx = StadiumAssetTransaction(self.root, Mock())
        staged = tx.stage / rel
        staged.parent.mkdir(parents=True)
        staged.write_bytes(b'new model')
        staged.chmod(stat.S_IREAD)
        tx.commit(set(), lambda: None)
        self.assertEqual(original.read_bytes(), b'new model')
        self.assertFalse(original.stat().st_file_attributes & 1)
        tx.rollback()
        self.assertEqual(original.read_bytes(), b'working model')
        self.assertTrue(original.stat().st_file_attributes & 1)

    def app(self):
        assignments = {('Scoreboard', '10'): 'Missing package', ('Scoreboard', '0'): 'Default TV'}
        self.put('FSW/ScoreBoard/native.big', b'native')
        self.put('ScoreBoardGBD/Default TV/game/score.big')
        app = SimpleNamespace(exedir=self.root, ScoreBoard=self.root/'ScoreBoardGBD',
            TVLogo=self.root/'TVLogoGBD', TVdata=self.root/'data/ui/game/overlays',
            Scoredata=self.root/'data/ui', TOURROUNDID='11', TOURNAME='10', HID='1',
            log=Mock(), _set_display=Mock(), module_enabled=lambda n: n in {'TvLogo', 'ScoreBoard'},
            settings_ini=SimpleNamespace(read=lambda k,s: assignments.get((s,k), ''),
                key_exists=lambda k,s: bool(assignments.get((s,k)))),
            _show_asset_loading=Mock(), _update_asset_loading=Mock(), _hide_asset_loading=Mock())
        runtime = AssetRuntime(app)
        runtime.update_audio_overview = Mock()
        return app, runtime

    def test_broken_tv_logo_cannot_block_scoreboard_and_missing_package_uses_default(self):
        app, runtime = self.app()
        with patch('server16_py.asset_runtime.copy_tvlogo', side_effect=PermissionError('logo locked')):
            runtime.apply_scoreboard_runtime()
        self.assertEqual((app.Scoredata/'game/score.big').read_bytes(), b'new scoreboard')
        self.assertEqual((app.Scoredata/'game/native.big').read_bytes(), b'native')
        app._set_display.assert_any_call('scoreboard', 'Default TV')
        self.assertTrue(any('missing or incomplete' in str(c) for c in app.log.call_args_list))

    def test_corrupt_preference_does_not_disable_automatic_scoreboard(self):
        app, runtime = self.app()
        self.put('ModCarrerMode/config/scoreboard.ini', b'invalid ini')
        runtime.apply_scoreboard_runtime()
        self.assertTrue((app.Scoredata/'game/score.big').is_file())

    def test_stadium_failure_does_not_prevent_scoreboard_or_movie(self):
        app = SimpleNamespace(HID='1', AID='2', TOURNAME='10', TOURROUNDID='11', STADID='',
            log=Mock(), _set_progress=Mock(), entrance_props_runtime=SimpleNamespace(prepare_match=Mock()),
            module_enabled=lambda n: True, apply_stadium_runtime=Mock(side_effect=PermissionError('stadium denied')),
            apply_scoreboard_runtime=Mock(), apply_movie_runtime=Mock(), _stadium_task_running=False)
        self.assertFalse(Server16App.apply_all_runtime(app))
        app.apply_scoreboard_runtime.assert_called_once()
        app.apply_movie_runtime.assert_called_once()

    def test_server_ini_edit_replaces_readonly_active_scoreboard(self):
        from server16_py.settings_editor import SettingsSectionFrame
        app,runtime=self.app()
        runtime.apply_scoreboard_runtime()
        target=app.Scoredata/'game/score.big';self.assertEqual(target.read_bytes(),b'new scoreboard')
        target.chmod(stat.S_IREAD)
        self.put('ScoreBoardGBD/Other/game/score.big',b'server assignment')
        original=app.settings_ini.read
        app.settings_ini.read=lambda key,section:'Other' if section=='Scoreboard' and key==app.TOURNAME else original(key,section)
        app.apply_all_runtime=runtime.apply_scoreboard_runtime;app.refresh_modules=Mock()
        editor=SimpleNamespace(app=app,spec=SimpleNamespace(section='Scoreboard'),status_var=SimpleNamespace(get=lambda:'',set=Mock()),tr=lambda key:key)
        SettingsSectionFrame._apply_runtime(editor)
        self.assertEqual(target.read_bytes(),b'server assignment')
        self.assertFalse((self.root/'ModCarrerMode/config/scoreboard.ini').exists())

    def test_unrelated_server_edit_does_not_write_legacy_preference(self):
        from server16_py.settings_editor import SettingsSectionFrame
        app,runtime=self.app()
        before=b'[Scoreboard]\nMode=native\n'
        self.put('ModCarrerMode/config/scoreboard.ini',before)
        app.refresh_modules=Mock();app.apply_all_runtime=Mock(return_value=True)
        editor=SimpleNamespace(app=app,spec=SimpleNamespace(section='Movies'),status_var=SimpleNamespace(get=lambda:'',set=Mock()),tr=lambda key:key)
        SettingsSectionFrame._apply_runtime(editor)
        self.assertEqual((self.root/'ModCarrerMode/config/scoreboard.ini').read_bytes(),before)

    def test_explicit_server_stadium_edit_supersedes_picker_but_other_edits_do_not(self):
        from server16_py.settings_editor import SettingsSectionFrame
        app = SimpleNamespace(_manual_stadium_override=('fixture', 'selected'),
            _last_stadium_applied_signature=('previous',), refresh_modules=Mock(),
            apply_all_runtime=Mock(return_value=True), log=Mock())
        editor=SimpleNamespace(app=app, spec=SimpleNamespace(section='Movies'),
            status_var=SimpleNamespace(get=lambda:'',set=Mock()),tr=lambda key:key)
        SettingsSectionFrame._apply_runtime(editor)
        self.assertEqual(app._manual_stadium_override, ('fixture', 'selected'))
        editor.spec.section='stadium'
        SettingsSectionFrame._apply_runtime(editor)
        self.assertIsNone(app._manual_stadium_override)
        self.assertIsNone(app._last_stadium_applied_signature)

    def test_equal_size_and_timestamp_do_not_skip_a_different_scoreboard(self):
        source=self.put('package/score.big', b'NEW SCORE')
        target=self.put('active/score.big', b'OLD SCORE')
        os.utime(target, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
        self.assertTrue(file_tools._copy_file_if_needed(source, target))
        self.assertEqual(target.read_bytes(), b'NEW SCORE')

    def context_app(self):
        return SimpleNamespace(HID='', AID='', TOURNAME='', TOURROUNDID='', STADID='',
            Stadiumtype='first', offsets=Offsets(), _last_runtime_signature=None,
            _read_legacy_team_context=lambda: ('1','2'), _read_dashboard_pointer=lambda *args: 0,
            _try_read_context_int=lambda name,*args: None if name.startswith('S-') else '10',
            audio_profiles=SimpleNamespace(sync=Mock()), _set_display=Mock(), _update_team_logo=Mock(),
            _resolve_team_name=lambda value: value, _update_live_match_stats=Mock(), log=Mock(),
            tr=lambda value: value, _should_auto_apply_runtime=lambda page: page.endswith('KickOffHub'),
            apply_all_runtime=Mock(return_value=True))

    def test_same_fixture_observed_before_setup_still_applies_and_does_not_reroll(self):
        app = self.context_app()
        Server16App.refresh_live_context(app, 'game/screens/playNow/SelectTeam')
        app.apply_all_runtime.assert_not_called()
        Server16App.refresh_live_context(app, 'game/screens/playNow/KickOffHub')
        Server16App.refresh_live_context(app, 'game/screens/playNow/KickOffHub')
        app.apply_all_runtime.assert_called_once()

    def test_failed_first_application_retries_same_context_after_backoff(self):
        app = self.context_app()
        app.apply_all_runtime.side_effect = [False, True]
        with patch('server16_py.app.time.monotonic', side_effect=[100.,100.,101.,103.]):
            for _ in range(3):Server16App.refresh_live_context(app, 'game/screens/playNow/KickOffHub')
        self.assertEqual(app.apply_all_runtime.call_count, 2)

    def test_successful_reads_between_stadium_errors_do_not_flood_log(self):
        app = SimpleNamespace(memory=SimpleNamespace(get_int=Mock()), _last_context_error=None,
            log=Mock(), _log_pointer_debug=Mock())
        with patch('server16_py.app.time.monotonic', return_value=100.):
            for _ in range(20):
                app.memory.get_int.side_effect=MemoryAccessError('Null pointer')
                self.assertIsNone(Server16App._try_read_context_int(app, 'S-FIRST', 1, [1], 'KickOffHub'))
                app.memory.get_int.side_effect=None
                app.memory.get_int.return_value=10
                self.assertEqual(Server16App._try_read_context_int(app, 'T-TOUR', 1, [1], 'KickOffHub'), '10')
        app.log.assert_called_once()
        app._log_pointer_debug.assert_called_once()


if __name__ == '__main__':unittest.main()
