import tempfile
import threading
import unittest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
from server16_py.d3d_injector import D3DOverlayInjector, installed_overlay_path


class OverlayReattachTests(unittest.TestCase):
    def test_installed_host_plugin_takes_priority_over_frozen_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);game=root/'game';resources=root/'frozen'
            installed=game/'ModCarrerMode/mods/server16_overlay/cgfs16_overlay.dll'
            bundled=resources/'bin/cgfs16_overlay.dll'
            for path,data in ((installed,b'installed'),(bundled,b'stale bundle')):
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            expected=installed_overlay_path(game,resources)
            self.assertEqual(expected,installed)
            instance=self.injector(expected)
            with patch('server16_py.d3d_injector._loaded_overlay_path',return_value=installed):
                self.assertTrue(instance.inject(123))
                instance._do_inject.assert_not_called()

    def test_fallback_without_host_plugin_uses_game_bin_before_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);game=root/'game';resources=root/'frozen'
            bundled=resources/'bin/cgfs16_overlay.dll'
            bundled.parent.mkdir(parents=True);bundled.write_bytes(b'bundled')
            self.assertEqual(installed_overlay_path(game,resources),bundled)
            local=game/'bin/cgfs16_overlay.dll'
            local.parent.mkdir(parents=True);local.write_bytes(b'installed')
            self.assertEqual(installed_overlay_path(game,resources),local)

    def injector(self, path):
        instance=D3DOverlayInjector.__new__(D3DOverlayInjector)
        instance._dll_path=str(path)
        instance._ready=True
        instance._injected_pid=0
        instance._lock=threading.Lock()
        instance._do_inject=Mock(return_value=True)
        return instance

    def test_server_restart_reuses_matching_native_dll(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'new.dll';loaded=root/'loaded.dll'
            source.write_bytes(b'same native build');loaded.write_bytes(source.read_bytes())
            instance=self.injector(source)
            with patch('server16_py.d3d_injector._loaded_overlay_path',return_value=loaded):
                self.assertTrue(instance.inject(123))
                instance._do_inject.assert_not_called()
                self.assertEqual(instance._injected_pid,123)

    def test_conflicting_native_version_never_installs_another_hook(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'new.dll';loaded=root/'loaded.dll'
            source.write_bytes(b'new');loaded.write_bytes(b'old')
            instance=self.injector(source)
            with patch('server16_py.d3d_injector._loaded_overlay_path',return_value=loaded):
                self.assertFalse(instance.inject(123))
                instance._do_inject.assert_not_called()

    def test_unknown_inventory_is_not_treated_as_no_existing_module(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'overlay.dll';source.write_bytes(b'native')
            instance=self.injector(source)
            with patch('server16_py.d3d_injector._loaded_overlay_path',side_effect=OSError('lost process')):
                self.assertFalse(instance.inject(123))
                instance._do_inject.assert_not_called()
            with patch('server16_py.d3d_injector._loaded_overlay_path',return_value=None):
                self.assertFalse(instance.inject(123))
                instance._do_inject.assert_not_called()

    def test_missing_plugin_never_starts_a_process_even_if_old_helper_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'cgfs16_overlay.dll';source.write_bytes(b'plugin')
            (root/'cgfs16_inject.exe').write_bytes(b'retired helper')
            instance=self.injector(source)
            with patch('server16_py.d3d_injector._loaded_overlay_path',return_value=None),patch.object(subprocess,'run') as run:
                self.assertTrue(instance.is_ready())
                for _ in range(4):self.assertFalse(instance.inject(123))
                run.assert_not_called();instance._do_inject.assert_not_called()


if __name__=='__main__':unittest.main()
