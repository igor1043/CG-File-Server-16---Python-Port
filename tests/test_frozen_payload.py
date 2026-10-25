import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('frozen_payload',Path(__file__).resolve().parents[1]/'scripts/frozen_payload.py')
payload=importlib.util.module_from_spec(spec);spec.loader.exec_module(payload)
class FrozenPayloadTests(unittest.TestCase):
    def test_build_tools_and_bytecode_are_excluded(self):
        for name in ('Lib/site-packages/pip/_internal/network/__pycache__/lazy_wheel.cpython-39.pyc',
                     'Lib/site-packages/pip/__init__.py','Lib/site-packages/setuptools/__init__.py',
                     'Lib/site-packages/wheel/__init__.py','Lib/site-packages/pythonnet-3.0.5.dist-info/METADATA',
                     'Lib/site-packages/distutils-precedence.pth','Scripts/pip.exe'):
            self.assertFalse(payload.include_bridge_path(name),name)
    def test_bridge_runtime_and_dependencies_are_kept(self):
        for name in ('python.exe','python39.dll','python39.zip','python39._pth','_ctypes.pyd',
                     'Lib/site-packages/clr.py','Lib/site-packages/pythonnet/runtime/Python.Runtime.dll',
                     'Lib/site-packages/clr_loader/ffi/__init__.py','Lib/site-packages/cffi/api.py',
                     'Lib/site-packages/_cffi_backend.cp39-win32.pyd','Lib/site-packages/pycparser/__init__.py',
                     'Lib/site-packages/packaging/version.py'):
            self.assertTrue(payload.include_bridge_path(name),name)
