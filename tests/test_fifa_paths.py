import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.app import Server16App
from server16_py.dialogs import BaseDialog, FifaLocationWarningDialog
from server16_py.ini_file import SessionIniFile
from server16_py.localization import LocalizationManager


class FifaPathsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.app = SimpleNamespace(
            base_dir=self.root, exedir=self.root,
            settings=SimpleNamespace(fifa_exe='default'), log=Mock(),
            audio_profiles=Mock(), _load_module_states=Mock(),
            _refresh_bh_button_state=Mock(), _update_audio_overview=Mock(),
            _load_team_database=Mock(), _first_existing=lambda *paths: paths[0],
            _dismiss_launch_splash=Mock(),
        )
        self.app._auto_detect_fifa_exe = lambda: Server16App._auto_detect_fifa_exe(self.app)

    def test_startup_prefers_local_fifa_over_saved_other_installation(self):
        local = self.root / 'fifa16.exe'
        local.touch()
        other = self.root / 'other' / 'fifa16.exe'
        other.parent.mkdir()
        other.touch()
        self.app.settings.fifa_exe = str(other)
        Server16App.setuppaths(self.app, load_team_database=False)
        self.assertEqual(self.app.fifaEXE, str(local))
        self.assertEqual(self.app.settings.fifa_exe, str(local))
        self.assertEqual(self.app.settings_ini.path, self.root / 'FSW/settings.ini')
        self.assertFalse(self.app.settings_ini.path.exists())

    def test_saved_external_installation_remains_available_without_local_fifa(self):
        other = self.root / 'other.exe'
        other.touch()
        self.app.settings.fifa_exe = str(other)
        self.assertEqual(self.app._auto_detect_fifa_exe(), other)
        other.unlink()
        (self.root / 'fifa16.exe').mkdir()  # A directory is not an executable.
        self.assertIsNone(self.app._auto_detect_fifa_exe())
        Server16App.setuppaths(self.app, load_team_database=False)
        self.assertEqual(self.app.fifaEXE, 'default')

    def test_missing_ini_does_not_create_partial_discord_configuration(self):
        self.app.fifaEXE = str(self.root / 'fifa16.exe')
        self.app.settings_ini = SessionIniFile(self.root / 'FSW/settings.ini')
        self.app._discord_rpc_enabled = False
        self.app.discord_rpc = Mock()
        self.app.module_vars = {}
        Server16App._load_module_states(self.app)
        self.assertFalse(self.app.settings_ini.path.exists())

    def test_missing_ini_warning_translated_and_existing_ini_untouched(self):
        locales = Path(__file__).resolve().parents[1] / 'server16_py/locales'
        for language in ('pt', 'en', 'es'):
            translator = LocalizationManager(locales, language)
            self.app.tr = translator.translate
            with patch('server16_py.app.messagebox.showwarning') as warning:
                self.assertFalse(Server16App._check_fifa_settings(self.app))
            title, body = warning.call_args.args
            self.assertNotIn('message.', title)
            self.assertNotIn('message.warning.', body)
            self.assertIn(str(self.root / 'FSW/settings.ini'), body)
        path = self.root / 'FSW/settings.ini'
        path.parent.mkdir()
        path.write_bytes(b'[Modules]\nStadium=1\n')
        original = path.read_bytes()
        with patch('server16_py.app.messagebox.showwarning') as warning:
            self.assertTrue(Server16App._check_fifa_settings(self.app))
            warning.assert_not_called()
        self.assertEqual(path.read_bytes(), original)

    def test_location_dialog_translates_title_before_tk_initialization(self):
        owner = SimpleNamespace(tr=Mock(return_value='Aviso de localização do FIFA 16'))
        with patch.object(BaseDialog, '__init__', side_effect=RuntimeError('stop before Tk')) as init:
            with self.assertRaisesRegex(RuntimeError, 'stop before Tk'):
                FifaLocationWarningDialog(owner, self.root, self.root)
        owner.tr.assert_called_once_with('dialog.fifa_location.title')
        self.assertEqual(init.call_args.args[1], 'Aviso de localização do FIFA 16')

    def test_missing_ini_stops_bootstrap_and_launch(self):
        self.app._auto_detect_fifa_exe = Mock(return_value=self.root / 'fifa16.exe')
        self.app.setuppaths = Mock()
        self.app._check_fifa_settings = Mock(return_value=False)
        self.app.apply_bootstrap_files = Mock()
        self.app.launch_fifa = Mock()
        Server16App.start_overlay_session(self.app)
        self.app.apply_bootstrap_files.assert_not_called()
        self.app.launch_fifa.assert_not_called()


if __name__ == '__main__':
    unittest.main()
