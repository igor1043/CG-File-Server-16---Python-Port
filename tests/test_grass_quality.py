import configparser
import ctypes
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from server16_py.grass_quality_runtime import (
    BUILD_TIMESTAMP, GRASS_RENDER, GRASS_VTABLE, GrassQualityRuntime,
    GrassQualitySettings, detail_ranges,
)
from server16_py.match_state import NativeMatchScene


class FakeMemory:
    base_module=0x140000000
    process_id=77
    renderer=0x100000
    owner=0x200000
    params=0x300000

    def __init__(self):
        self.process_handle=1
        self.data={}
        self.writes=[]
        self.kernel32=SimpleNamespace(WriteProcessMemory=self.write)
        self.put(self.base_module,b'MZ');self.put(self.base_module+0x3C,struct.pack('<I',0x100))
        self.put(self.base_module+0x100,b'PE\0\0\0\0\0\0'+struct.pack('<I',BUILD_TIMESTAMP))
        self.put(self.base_module+GRASS_RENDER,struct.pack('<Q',self.renderer))
        self.put(self.renderer,bytes(0x600));self.put(self.owner,bytes(0x6A8));self.put(self.params,bytes(0xC0))
        for offset in (0x1B0,0x500):self.put(self.renderer+offset,struct.pack('<Q',self.owner))
        self.put(self.owner,struct.pack('<Q',self.base_module+GRASS_VTABLE))
        self.put(self.owner+0x4B0,struct.pack('<i',1));self.put(self.owner+0x4C8,struct.pack('<2i',6800,10500))
        self.put(self.owner+0x5E4,b'\1');self.put(self.owner+0x668,struct.pack('<Q',self.params))
        for address in (self.owner+0x214,self.renderer+0x94):self.put(address,struct.pack('<2f',200,400))
        for address in (self.params+0x24,self.renderer+0xA0):self.put(address,struct.pack('<5f',1,100,900,1000,1100))

    def put(self,address,data):self.data.update({address+i:v for i,v in enumerate(data)})
    def read_process_memory(self,address,size):
        try:return bytes(self.data[address+i] for i in range(size))
        except KeyError:raise RuntimeError('Unmapped memory')
    def read_int64(self,address):return struct.unpack('<Q',self.read_process_memory(address,8))[0]
    def read_uint32(self,address):return struct.unpack('<I',self.read_process_memory(address,4))[0]
    def is_open(self):return bool(self.process_handle)
    def write(self,handle,address,buffer,size,count):
        address=address.value;data=ctypes.string_at(buffer,size)
        self.put(address,data);self.writes.append((address,data))
        ctypes.cast(count,ctypes.POINTER(ctypes.c_size_t))[0]=size
        return True


class GrassQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.memory=FakeMemory()
        self.app=SimpleNamespace(base_dir=self.root,memory=self.memory,lastpagename='game/screens/inGame',log=Mock())
        self.runtime=GrassQualityRuntime(self.app)
        self.runtime.controller=True
        self.scene=patch('server16_py.grass_quality_runtime.read_native_match_scene',return_value=NativeMatchScene(55,15,False))
        self.scene.start()

    def tearDown(self):
        self.runtime.close();self.scene.stop();self.tmp.cleanup()

    def test_settings_default_off_persist_and_preserve_unrelated_values(self):
        store=self.runtime.store;self.assertFalse(store.enabled())
        store.set_enabled(True);self.assertTrue(GrassQualitySettings(self.root).enabled())
        with store.path.open('a') as file:file.write('\n[unrelated]\nvalue=keep\n')
        store.set_enabled(False);self.assertFalse(store.enabled());self.assertIn('value = keep',store.path.read_text())
        with self.assertRaises(ValueError):store.set_enabled(1)

    def test_corrupt_settings_never_enable_or_overwrite_the_original_file(self):
        store=self.runtime.store;store.path.parent.mkdir(parents=True,exist_ok=True)
        store.path.write_text('broken configuration')
        self.runtime.next_tick=0;self.runtime.tick()
        self.assertFalse(self.runtime.active);self.assertFalse(self.memory.writes)
        with self.assertRaises(ValueError):self.runtime.set_enabled(True)
        self.assertEqual(store.path.read_text(),'broken configuration')

    def test_apply_only_known_grass_scalars_and_toggle_restores_exact_originals(self):
        original=dict(self.memory.data)
        self.runtime.set_enabled(True);self.assertTrue(self.runtime.active)
        self.assertEqual({a for a,_ in self.memory.writes}, {self.memory.owner+0x214,self.memory.renderer+0x94,self.memory.params+0x24,self.memory.renderer+0xA0})
        self.assertEqual(struct.unpack('<2f',self.memory.read_process_memory(self.memory.owner+0x214,8)),(8000,12000))
        self.assertEqual(struct.unpack('<5f',self.memory.read_process_memory(self.memory.params+0x24,20)),(400,700,900,1000,1100))
        self.runtime.set_enabled(False);self.assertEqual(self.memory.data,original);self.assertFalse(self.runtime.active)

    def test_wrong_build_or_unloaded_object_cannot_write(self):
        self.memory.put(self.memory.base_module+0x108,struct.pack('<I',0))
        self.runtime.set_enabled(True);self.assertFalse(self.memory.writes);self.assertFalse(self.runtime.active)
        self.memory.put(self.memory.base_module+0x108,struct.pack('<I',BUILD_TIMESTAMP))
        self.memory.put(self.memory.owner,struct.pack('<Q',0x12345))
        self.runtime.next_tick=0;self.runtime.tick();self.assertFalse(self.memory.writes)

    def test_stale_pointer_is_never_restored_into_replacement_object(self):
        self.runtime.set_enabled(True)
        self.memory.put(self.memory.renderer+0x1B0,struct.pack('<Q',0x44444))
        self.memory.writes.clear();self.runtime.set_enabled(False)
        self.assertFalse(self.memory.writes);self.assertFalse(self.runtime.active)

    def test_restore_preserves_native_changes_and_recaptures_new_camera_detail(self):
        self.runtime.set_enabled(True)
        native=struct.pack('<5f',100,250,900,1000,1100)
        self.memory.put(self.memory.params+0x24,native)
        self.runtime.next_tick=0;self.runtime.tick()
        self.runtime.set_enabled(False)
        self.assertEqual(self.memory.read_process_memory(self.memory.params+0x24,20),native)
        self.runtime.set_enabled(True)
        other=struct.pack('<2f',600,1000);self.memory.put(self.memory.owner+0x214,other)
        self.runtime.set_enabled(False)
        self.assertEqual(self.memory.read_process_memory(self.memory.owner+0x214,8),other)

    def test_menu_exit_restores_and_new_process_does_not_write_old_addresses(self):
        original=dict(self.memory.data);self.runtime.set_enabled(True)
        self.app.lastpagename='game/screens/career/Home';self.runtime.next_tick=0;self.runtime.tick()
        self.assertEqual(self.memory.data,original)
        self.app.lastpagename='game/screens/inGame';self.runtime.next_tick=0;self.runtime.tick()
        self.memory.process_id=88;self.memory.put(self.memory.renderer+0x1B0,struct.pack('<Q',0))
        self.memory.writes.clear();self.runtime.next_tick=0;self.runtime.tick();self.assertFalse(self.memory.writes)

    def test_details_never_extend_total_draw_range_or_accept_nan_unordered_values(self):
        for values in ((1,100,900,1000,1100),(100,200,250,300,500),(600,700,900,1000,1100)):
            result=detail_ranges(values);self.assertEqual(result[2:],values[2:]);self.assertEqual(tuple(sorted(result)),result)
        for values in ((1,100,float('nan'),1000,1100),(400,100,900,1000,1100),(1,100,900,1000,30000)):
            with self.assertRaises(ValueError):detail_ranges(values)

    @patch('server16_py.GRASS_QUALITY_AVAILABLE',True)
    def test_graphics_switch_applies_immediately_and_back_keeps_the_choice(self):
        from server16_py.match_hub_panel import MatchHubPanel
        self.app._grass_quality_runtime=self.runtime;self.app._resolve_fifa_pid=lambda:77
        selector=SimpleNamespace(app=self.app,context=('match',1),_context=lambda:('match',1),match_eligible=lambda:True,render=Mock())
        panel=MatchHubPanel(selector);panel.page='graphics'
        self.assertEqual(panel.items()[1][0],'Gramado em alta qualidade')
        panel.activate(1);self.assertTrue(self.runtime.enabled);self.assertTrue(self.runtime.active)
        panel.activate(2);self.assertEqual(panel.page,'home');self.assertTrue(self.runtime.store.enabled())
        panel.page='graphics';panel.activate(1);self.assertFalse(self.runtime.active)

    def test_hidden_release_has_no_switch_hint_or_activation_shortcut(self):
        from server16_py.match_hub_panel import MatchHubPanel
        import server16_py as features
        self.assertFalse(features.GRASS_QUALITY_AVAILABLE)
        self.app._resolve_fifa_pid=lambda:77
        selector=SimpleNamespace(app=self.app,context=('match',1),_context=lambda:('match',1),match_eligible=lambda:True,render=Mock())
        with patch('server16_py.match_hub_panel.grass_quality_runtime',side_effect=AssertionError('Hidden runtime was accessed')):
            panel=MatchHubPanel(selector)
            self.assertNotIn('gramado',' '.join(text for row in panel.items() for text in row).casefold())
            panel.page='graphics'
            self.assertEqual([row[0] for row in panel.items()],['Física de roupas','Voltar'])
            panel.tick();panel.activate(2)
            self.assertEqual(panel.page,'graphics')
            panel.handle(16,2);self.assertEqual(panel.page,'home')
        self.assertFalse(self.runtime.store.enabled())
        self.assertFalse(self.memory.writes)


if __name__=='__main__':unittest.main()
