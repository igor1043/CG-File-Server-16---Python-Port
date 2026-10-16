import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from server16_py.cloth_motion_switch import ClothMotionSwitch

class ClothMotionSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.switch=ClothMotionSwitch(self.root);self.switch.ini_path.parent.mkdir(parents=True)
        self.switch.dll_path.write_bytes(b'fixture DLL')
        self.list_before=b'# mod list\r\nother\\module.dll\r\ncloth_motion\\cloth_motion.dll\r\nlast\\module.dll\r\n'
        self.ini_before=b'[other]\r\nenabled=0\r\n[cloth_motion]\r\n; keep tuning\r\nenabled=1\r\nsolver_hz=120\r\n'
        self.switch.list_path.write_bytes(self.list_before);self.switch.ini_path.write_bytes(self.ini_before)
    def tearDown(self):self.temp.cleanup()
    def test_off_on_preserves_other_modules_and_tuning(self):
        self.assertTrue(self.switch.enabled());self.switch.set_enabled(False);self.assertFalse(self.switch.enabled())
        self.assertEqual(self.switch.list_path.read_bytes().count(b'cloth_motion\\cloth_motion.dll'),1)
        self.assertIn(b'; keep tuning\r\nenabled=0\r\nsolver_hz=120',self.switch.ini_path.read_bytes())
        self.switch.set_enabled(True);self.assertTrue(ClothMotionSwitch(self.root).enabled())
        self.assertEqual(self.switch.ini_path.read_bytes(),self.ini_before)
    def test_duplicates_and_slashes(self):
        self.switch.list_path.write_bytes(self.list_before+b'CLOTH_MOTION/CLOTH_MOTION.DLL\r\n')
        self.switch.set_enabled(True)
        self.assertEqual(self.switch.list_path.read_bytes().lower().count(b'cloth_motion'),2)
    def test_unconfigured_starts_off_and_explicit_choice_survives_reopen(self):
        for data in (b'[other]\nenabled=1\n',b'[cloth_motion]\nsolver_hz=120\n',
                     b'[cloth_motion]\nenabled=invalid\n',b'[cloth_motion]\nenabled=0\n'):
            self.switch.ini_path.write_bytes(data)
            self.assertFalse(ClothMotionSwitch(self.root).enabled())
        self.switch.set_enabled(True)
        self.assertTrue(ClothMotionSwitch(self.root).enabled())
        self.switch.set_enabled(False)
        self.assertFalse(ClothMotionSwitch(self.root).enabled())
    def test_missing_payload_does_not_modify_list(self):
        self.switch.dll_path.unlink()
        with self.assertRaises(FileNotFoundError):self.switch.set_enabled(True)
        self.assertEqual(self.switch.list_path.read_bytes(),self.list_before)
        self.switch.set_enabled(False);self.assertFalse(self.switch.enabled())
    def test_write_failure_restores_prior_setting(self):
        import server16_py.cloth_motion_switch as module
        original=module._atomic
        def failing(path,data):
            if path==self.switch.list_path:raise OSError('simulated write failure')
            original(path,data)
        with patch.object(module,'_atomic',side_effect=failing):
            with self.assertRaises(OSError):self.switch.set_enabled(False)
        self.assertEqual(self.switch.ini_path.read_bytes(),self.ini_before)
        self.assertEqual(self.switch.list_path.read_bytes(),self.list_before)
    def test_real_ui_handler_persists_without_a_window(self):
        source=Path(__file__).resolve().parents[1]/'server16_py/app.py';tree=ast.parse(source.read_text(encoding='utf-8-sig'))
        methods=[node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name in {'_on_module_toggle','module_enabled'}]
        self.assertEqual(len(methods),2)
        namespace={'ClothMotionSwitch':ClothMotionSwitch}
        future=ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[future]+methods,type_ignores=[])),str(source),'exec'),namespace)
        class FakeApp:
            exedir=self.root
            module_states={}
            def log(self,*args):pass
        class Var:
            def get(self):return False
        app=FakeApp();namespace['_on_module_toggle'](app,'ClothPhysics',Var())
        self.assertFalse(namespace['module_enabled'](app,'ClothPhysics'))
        self.assertFalse(self.switch.enabled())

if __name__=='__main__':unittest.main()
