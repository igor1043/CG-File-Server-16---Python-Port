import configparser
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from server16_py.entrance_props_runtime import EntrancePropsRuntime, resolve_asset
from server16_py.match_presentation import MatchPresentation, PresentationOptions


class EntrancePropsTests(unittest.TestCase):
    def test_unsupported_ceremony_does_not_interrupt_other_match_assets(self):
        from server16_py.app import Server16App
        with tempfile.TemporaryDirectory() as tmp:
            app = SimpleNamespace(exedir=Path(tmp), HID='1043', AID='567', TOURNAME='9999', TOURROUNDID='',
                                  STADID='1', log=Mock(), _set_progress=Mock(), _set_display=Mock(),
                                  module_enabled=lambda name: True, _stadium_task_running=False,
                                  apply_stadium_runtime=Mock(), apply_scoreboard_runtime=Mock(), apply_movie_runtime=Mock())
            app.entrance_props_runtime = EntrancePropsRuntime(app)
            Server16App.apply_all_runtime(app)
            app.apply_stadium_runtime.assert_called_once()
            app.apply_scoreboard_runtime.assert_called_once()
            app.apply_movie_runtime.assert_called_once()
            self.assertEqual(json.loads((app.exedir/'runtime/entrance_props_selection.json').read_text())['status'], 'settings_missing')

    def package(self, root, identifier='1615'):
        directory = root / 'data/sceneassets/entrance_props/competitions' / identifier
        directory.mkdir(parents=True)
        raw = b'RX3l' + struct.pack('<3I', 0, 32, 1) + b'\0'*16
        metadata = configparser.ConfigParser()
        metadata['asset'] = {'schema': '1', 'model_bytes': '32', 'texture_bytes': '32',
                             'model_sha256': hashlib.sha256(raw).hexdigest(),
                             'texture_sha256': hashlib.sha256(raw).hexdigest()}
        for name in ('model.rx3', 'template.rx3'):
            (directory / name).write_bytes(raw)
        with (directory / 'asset.ini').open('w') as file:
            metadata.write(file)
        return directory

    def settings(self, root, text='[movies]\n1615=BRA - Brasileirao Serie A\n'):
        path = root / 'FSW/settings.ini'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_configured_round_overrides_root_and_missing_round_inherits_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            group = self.package(root, '195')
            final = self.package(root, '245')
            self.settings(root, '[movies]\n195=UEFA - Champions League\n[comp]\n245=Estadio da final,10,3,0\n')
            self.assertEqual(resolve_asset(root, '195', '245'), (final, 'ready'))
            self.assertEqual(resolve_asset(root, '195', '219'), (group, 'ready'))
            (final/'asset.ini').unlink()
            self.assertEqual(resolve_asset(root, '195', '245'), (group, 'ready'))
            self.assertIsNone(resolve_asset(root, '9999')[0])
            self.assertIsNone(resolve_asset(root, '0')[0])

    def test_settings_ids_are_authoritative_and_reference_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = self.package(root)
            self.package(root, '9999')
            self.package(root, '1616')
            settings = self.settings(root, '[Scoreboard]\n1615=Nome de placar qualquer\n[unrelated]\n9999=Modelo\n')
            original = settings.read_bytes()
            mapping = root/'ModCarrerMode/config/entrance_competitions.ini'
            mapping.parent.mkdir(parents=True)
            mapping.write_text('[competitions]\n1615=9999\n9999=1615\n')
            (directory.parent/'REFERENCIA_IDS.txt').write_text('1615=9999\n')
            self.assertEqual(resolve_asset(root, '1615', '1616'), (directory, 'ready'))
            self.assertEqual(resolve_asset(root, '9999')[1], 'competition_unconfigured')
            self.assertEqual(settings.read_bytes(), original)
            self.settings(root, '[movies]\n9999=Outra competicao\n')
            self.assertEqual(resolve_asset(root, '1615')[1], 'competition_unconfigured')
            self.assertEqual(resolve_asset(root, '9999')[0].name, '9999')

    def test_missing_invalid_ids_and_same_size_corruption_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(resolve_asset(root, '1615')[1], 'settings_missing')
            self.settings(root)
            self.assertEqual(resolve_asset(root, '1615')[1], 'asset_missing')
            for identifier in ('../bad', 'C:/models', '0', '01615', '١٦١٥', '1000000', '-1'):
                self.assertIsNone(resolve_asset(root, identifier)[0])
            directory = self.package(root)
            self.assertEqual(resolve_asset(root, '1615')[1], 'ready')
            raw = bytearray((directory/'model.rx3').read_bytes()); raw[-1] = 1
            (directory/'model.rx3').write_bytes(raw)
            self.assertEqual(resolve_asset(root, '1615')[1], 'asset_checksum_invalid')
            (directory/'model.rx3').unlink()
            self.assertIsNone(resolve_asset(root, '1615')[0])

    def test_invalid_explicit_round_is_rejected_and_unrelated_malformed_ini_is_tolerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.package(root, '195')
            final = self.package(root, '245')
            self.settings(root, '[movies]\n195=Champions\n[COMP]\n245=Final\n[other]\nmalformed line without equals\n')
            (final/'model.rx3').write_bytes(b'bad')
            self.assertEqual(resolve_asset(root, '195', '245')[1], 'asset_size_invalid')
            self.assertEqual(resolve_asset(root, '195')[1], 'ready')

    def test_switch_default_yes_disabled_and_fixture_evidence_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); directory = self.package(root)
            self.settings(root)
            app = SimpleNamespace(exedir=root, HID='1043', AID='567', TOURNAME='1615', TOURROUNDID='', log=Mock())
            runtime = EntrancePropsRuntime(app)
            self.assertEqual(runtime.prepare_match(), directory)
            app.HID, app.AID = '2', '3'
            self.assertEqual(runtime.prepare_match(), directory)
            record = json.loads((root/'runtime/entrance_props_selection.json').read_text())
            self.assertEqual((record['home'], record['away']), ('2', '3'))
            options = PresentationOptions(entrance_props=False)
            MatchPresentation(root).save(options)
            self.assertIsNone(runtime.prepare_match())
            self.assertEqual(json.loads((root/'runtime/entrance_props_selection.json').read_text())['status'], 'disabled')
            self.assertFalse(list((root/'runtime').glob('*.tmp')))
