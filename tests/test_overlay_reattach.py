import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from server16_py.d3d_injector import D3DOverlayInjector


class OverlayReattachTests(unittest.TestCase):
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
                self.assertTrue(instance.inject(123))
                instance._do_inject.assert_called_once_with(123)


if __name__=='__main__':unittest.main()
