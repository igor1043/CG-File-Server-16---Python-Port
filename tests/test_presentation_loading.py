import ctypes
import hashlib
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.presentation_loading import PresentationLoading, prepare_assets, warm_file
from server16_py.presentation_bridge import decode_status, NAMES
from server16_py.d3d_injector import D3DOverlayInjector, _OverlayShared


class PresentationLoadingTests(unittest.TestCase):
    def fixture(self, root):
        def write(name, data):
            path = root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data.encode() if isinstance(data, str) else data)
            return path
        raw = b'RX3l'+struct.pack('<3I', 0, 32, 1)+bytes(16)
        write('ModCarrerMode/mods/enabled.txt', '\n'.join(f'{n}\\{n}.dll' for n in NAMES))
        write('ModCarrerMode/config/match_presentation.ini', '[match]\npyrotechnics=1\nentrance=1\ngoal=1\nentrance_props=1\n')
        for name in NAMES:
            write(f'ModCarrerMode/mods/{name}/{name}.dll', 'local test module')
        for name in ('var_cabin', 'smoke_machine'):
            for file in ('model.rx3', 'textures.rx3'):
                write(f'data/sceneassets/{name}/{file}', raw)
        write('data/sceneassets/particles/stadium_pyrotechnics_0.rx3', raw)
        xml = '<particleSystem><particleEffect>' + ''.join(
            f'<particleGroup name="group{i}"><particleAction className="ParticleActionEmitBox"><parameter name="bRespectExternalTrigger" value="1"/></particleAction></particleGroup>' for i in range(11))+'</particleEffect></particleSystem>'
        write('data/sceneassets/particles/stadium_pyrotechnics_0.lnx', xml)
        write('FSW/settings.ini', '[comp]\n1615=League\n')
        folder = 'data/sceneassets/entrance_props/competitions/1615/'
        for name in ('model.rx3', 'template.rx3'):
            write(folder+name, raw)
        digest = hashlib.sha256(raw).hexdigest()
        write(folder+'asset.ini', f'[asset]\nschema=1\nmodel_bytes=32\ntexture_bytes=32\nmodel_sha256={digest}\ntexture_sha256={digest}\n')
        return SimpleNamespace(exedir=root, HID='1043', AID='567', TOURNAME='1615', TOURROUNDID='',
            lastpagename='game/screens/playNow/KickOffHub', memory=SimpleNamespace(process_id=1234), log=Mock())

    def test_prepares_every_module_and_publishes_preview_without_firing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.fixture(root)
            before = (root/'ModCarrerMode/config/match_presentation.ini').read_bytes()
            events = []
            prepare_assets(snapshot, threading.Event(), lambda *e: events.append(e))
            self.assertEqual([i for i, state, text in events if state == 'prepared'], list(range(4)))
            context = (root/'runtime/entrance_props_context.ini').read_text()
            self.assertIn('preview=1', context)
            self.assertIn('process_id=1234', context)
            self.assertEqual(before, (root/'ModCarrerMode/config/match_presentation.ini').read_bytes())

    def test_missing_var_does_not_block_smoke_or_pyrotechnics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.fixture(root)
            (root/'data/sceneassets/var_cabin/model.rx3').unlink()
            events = []
            prepare_assets(snapshot, threading.Event(), lambda *e: events.append(e))
            self.assertIn((2, 'error', 'Arquivo ausente'), events)
            self.assertIn((1, 'prepared', 'Arquivos preparados'), events)
            self.assertIn((3, 'prepared', 'Arquivos preparados'), events)

    def test_disabled_effects_are_not_read_or_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.fixture(root)
            path = root/'ModCarrerMode/config/match_presentation.ini'
            path.write_text('[match]\npyrotechnics=0\nentrance_props=0\n')
            (root/'data/sceneassets/particles/stadium_pyrotechnics_0.lnx').unlink()
            events = []
            prepare_assets(snapshot, threading.Event(), lambda *e: events.append(e))
            for i in (0, 1, 3):
                self.assertIn((i, 'skipped', 'Desativado'), events)
            self.assertIn('pyrotechnics=0', path.read_text())

    def test_corrupt_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'model.rx3'
            path.write_bytes(bytes(32))
            with self.assertRaises(ValueError):
                warm_file(path, threading.Event(), rx3=True)

    def test_cancelled_preparation_cannot_publish_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self.fixture(root)
            stop = threading.Event()
            stop.set()
            events = []
            prepare_assets(snapshot, stop, lambda *e: events.append(e))
            self.assertFalse(events)
            self.assertFalse((root/'runtime/entrance_props_context.ini').exists())

    def test_bridge_rejects_old_process_torn_and_stale_rows(self):
        words = [1, 1234]+[2, 3, 1000, 1]*4
        self.assertEqual(len(decode_status(struct.pack('<18I', *words), 1234, 1200)), 4)
        self.assertEqual(decode_status(struct.pack('<18I', *words), 1235, 1200), {})
        self.assertEqual(decode_status(struct.pack('<18I', *words), 1234, 7000), {})
        words[2] = 3
        self.assertNotIn(NAMES[0], decode_status(struct.pack('<18I', *words), 1234, 1200))

    def test_gameplay_has_no_asset_reads_workers_or_bridge_poll(self):
        app = SimpleNamespace(memory=SimpleNamespace(is_open=lambda: True), lastpagename='', _finish_asset_loading=Mock())
        bridge = SimpleNamespace(read=Mock(), close=Mock())
        runtime = PresentationLoading(app, bridge=bridge)
        runtime._configuration_stamp = Mock(side_effect=AssertionError('Gameplay file read'))
        runtime.tick()
        runtime._configuration_stamp.assert_not_called()
        bridge.read.assert_not_called()
        self.assertIsNone(runtime.thread)

    def test_preview_ready_then_native_ack_during_match_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self.fixture(root)
            app.memory.is_open = lambda: True
            app._kickoff_generation = 1
            app.STADID = '176'
            app._show_asset_loading = Mock()
            app._update_asset_loading = Mock()
            app._hide_asset_loading = Mock()
            app._finish_asset_loading = Mock()
            bridge = SimpleNamespace(read=Mock(return_value={}), close=Mock())
            runtime = PresentationLoading(app, bridge=bridge)
            with patch('server16_py.presentation_loading.threading.Thread') as worker, patch('server16_py.presentation_loading.time.monotonic', return_value=1):
                runtime.tick()
                worker.call_args.kwargs['target']()
            with patch('server16_py.presentation_loading.time.monotonic', return_value=2):
                runtime.tick()
            self.assertEqual(runtime.notice[2], 100)
            self.assertEqual(runtime.notice[0], 'Pré-jogo preparado')
            self.assertIn('VAR: Preparado para iniciar', runtime.notice[1])
            app._hide_asset_loading.assert_not_called()
            self.assertFalse(__import__('json').loads((root/'runtime/presentation_loading.json').read_text())['scene_confirmed'])
            app.lastpagename = 'TV/bumper'
            runtime._configuration_stamp = Mock(side_effect=AssertionError('Loading must not reread files'))
            with patch('server16_py.presentation_loading.time.monotonic', return_value=3):
                runtime.tick()
            self.assertTrue(runtime.tracking)
            self.assertEqual(runtime.notice[0], 'Carregando cena da partida')
            self.assertEqual(runtime.notice[2], 50)
            bridge.read.return_value = dict.fromkeys(NAMES, 3)
            with patch('server16_py.presentation_loading.time.monotonic', return_value=4):
                runtime.tick()
            self.assertIsNone(runtime.key)
            self.assertTrue(runtime.completed)
            app._show_asset_loading.assert_not_called()
            app._update_asset_loading.assert_not_called()
            app._hide_asset_loading.assert_not_called()
            app._finish_asset_loading.assert_not_called()
            bridge.read.reset_mock()
            with patch('server16_py.presentation_loading.time.monotonic', return_value=5):
                runtime.tick()
            bridge.read.assert_not_called()
            self.assertTrue(__import__('json').loads((root/'runtime/presentation_loading.json').read_text())['scene_confirmed'])

    def test_registered_waiting_loader_survives_absent_scene_heartbeat(self):
        words = [1, 1234]+[2, 1, 1000, 1]*4
        self.assertEqual(decode_status(struct.pack('<18I', *words), 1234, 7000), dict.fromkeys(NAMES, 1))

    def test_loading_poll_expires_and_leaves_no_gameplay_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self.fixture(Path(tmp))
            app.lastpagename = ''
            app.memory.is_open = lambda: True
            app.STADID = '176'
            app._show_asset_loading = Mock()
            app._update_asset_loading = Mock()
            app._hide_asset_loading = Mock()
            app._finish_asset_loading = Mock()
            bridge = SimpleNamespace(read=Mock(return_value={}), close=Mock())
            runtime = PresentationLoading(app, bridge=bridge)
            runtime.key = (str(app.exedir), 1234, 1, '1043', '567')
            runtime.rows = [('prepared', 'Arquivos preparados')]*4
            with patch('server16_py.presentation_loading.time.monotonic', return_value=1):
                runtime.tick()
            self.assertTrue(runtime.tracking)
            with patch('server16_py.presentation_loading.time.monotonic', return_value=17):
                runtime.tick()
            self.assertIsNone(runtime.key)
            app._show_asset_loading.assert_not_called()
            app._update_asset_loading.assert_not_called()
            app._hide_asset_loading.assert_not_called()
            app._finish_asset_loading.assert_not_called()
            bridge.read.reset_mock()
            with patch('server16_py.presentation_loading.time.monotonic', return_value=18):
                runtime.tick()
            bridge.read.assert_not_called()

    def test_loading_stops_on_exit_or_another_fixture(self):
        for page, home in (('game/screens/career/Hub', '1043'), ('', '1')):
            app = SimpleNamespace(memory=SimpleNamespace(is_open=lambda: True, process_id=1234),
                                  lastpagename=page, HID=home, AID='567', _finish_asset_loading=Mock())
            bridge = SimpleNamespace(read=Mock(), close=Mock())
            runtime = PresentationLoading(app, bridge=bridge)
            runtime.key = ('root', 1234, 1, '1043', '567')
            runtime.tick()
            self.assertIsNone(runtime.key)
            bridge.read.assert_not_called()

    def test_presentation_card_has_separate_memory_from_narrator_and_stadium(self):
        inj = D3DOverlayInjector.__new__(D3DOverlayInjector)
        inj._ready = True
        inj._shared = _OverlayShared()
        inj._shared.visible = inj._shared.narration_visible = 1
        inj._shared.stadium_name = 'Estádio'
        inj.show_asset('presentation', 'Recursos', 'Entradas: preparadas', 50)
        self.assertEqual(inj._shared.presentation_progress_x100, 5000)
        inj.hide_asset('presentation')
        self.assertEqual(inj._shared.narration_visible, 1)
        self.assertEqual(inj._shared.stadium_name, 'Estádio')
        self.assertEqual(ctypes.sizeof(_OverlayShared), 7208)

    def test_leaving_preview_cancels_old_hide_timer(self):
        from server16_py.app import Server16App
        app = SimpleNamespace(_asset_loading_hide_jobs={'presentation': 'old-fixture-timer'},
                              _asset_loading_started_at={'presentation': 1},
                              _asset_loading_fallback=set(), _d3d_injector=None, after_cancel=Mock())
        Server16App._finish_asset_loading(app, 'presentation')
        app.after_cancel.assert_called_once_with('old-fixture-timer')
        self.assertNotIn('presentation', app._asset_loading_hide_jobs)

    def test_old_worker_events_are_ignored_after_fixture_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = self.fixture(root)
            app.memory.is_open = lambda: True
            app._kickoff_generation = 1
            app.STADID = '176'
            app._show_asset_loading = Mock()
            app._update_asset_loading = Mock()
            app._hide_asset_loading = Mock()
            runtime = PresentationLoading(app, bridge=SimpleNamespace(read=Mock(return_value={}), close=Mock()))
            with patch('server16_py.presentation_loading.threading.Thread'), patch('server16_py.presentation_loading.time.monotonic', return_value=1):
                runtime.tick()
            old_generation = runtime.generation
            old_cancel = runtime.cancelled
            app.HID = '1'
            runtime.events.put((old_generation, 0, 'prepared', 'old fixture'))
            with patch('server16_py.presentation_loading.threading.Thread'), patch('server16_py.presentation_loading.time.monotonic', return_value=2):
                runtime.tick()
            self.assertTrue(old_cancel.is_set())
            self.assertNotEqual(runtime.generation, old_generation)
            self.assertEqual(runtime.rows[0][0], 'pending')


if __name__ == '__main__':
    unittest.main()
