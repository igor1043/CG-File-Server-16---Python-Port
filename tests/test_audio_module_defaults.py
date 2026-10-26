import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from server16_py.app import Server16App
from server16_py.ini_file import SessionIniFile, ensure_audio_module_defaults, module_setting_enabled


class AudioModuleDefaultsTests(unittest.TestCase):
    def test_missing_away_setting_defaults_on_but_does_not_enable_other_modules(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.ini'
            path.write_text('[modules]\nChants=1\n',encoding='utf8')
            settings=SessionIniFile(path)
            ensure_audio_module_defaults(settings)
            self.assertTrue(module_setting_enabled(SessionIniFile(path),'AwayChants'))
            self.assertFalse(module_setting_enabled(settings,'Movies'))
            self.assertEqual(settings.read('Chants','Modules'),'1')

    def test_manual_off_survives_reload_and_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.ini'
            path.write_text('[modules]\nAwayChants=1\nChants=1\n',encoding='utf8')
            app=SimpleNamespace(settings_ini=SessionIniFile(path),module_states={},log=Mock())
            Server16App._on_module_toggle(app,'AwayChants',SimpleNamespace(get=lambda:False))
            app.settings_ini=SessionIniFile(path)
            ensure_audio_module_defaults(app.settings_ini)
            self.assertFalse(Server16App.module_enabled(app,'AwayChants'))
            self.assertEqual(app.settings_ini.read('AwayChants','Modules'),'0')
            self.assertEqual(app.settings_ini.read('Chants','Modules'),'1')

    def test_missing_game_configuration_is_not_created(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'missing/settings.ini'
            ensure_audio_module_defaults(SessionIniFile(path))
            self.assertFalse(path.exists())
