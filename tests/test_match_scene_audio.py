import struct
import unittest
from types import SimpleNamespace
from server16_py.match_state import read_native_match_scene, GoalClockProgress


class NativeSceneAudioTests(unittest.TestCase):
    def memory(self):
        base, source, vtable = 0x140000000, 0x50000000, 0x1420FF390
        pointers = {base+0x3517C10: source, source: vtable,
                    vtable+0x30: base+0x39FEE10, vtable+0x70: base+0x3A00D60}
        memory = SimpleNamespace(base_module=base, read_int64=pointers.__getitem__,
            read_process_memory=lambda address,size: struct.pack('<B2xi',1,15))
        return memory, pointers

    def test_replay_is_not_live_even_with_gameplay_phase(self):
        memory, _ = self.memory()
        scene=read_native_match_scene(memory)
        self.assertTrue(scene.replay)
        self.assertFalse(scene.live)
        memory.read_process_memory=lambda *args: struct.pack('<B2xi',0,15)
        self.assertTrue(read_native_match_scene(memory).live)

    def test_unsupported_vtable_and_getters_are_rejected(self):
        for index in (0,1,2,3):
            memory,pointers=self.memory()
            pointers[list(pointers)[index]]=0
            self.assertIsNone(read_native_match_scene(memory))

    def test_torn_and_invalid_samples_are_rejected(self):
        for samples in ((struct.pack('<B2xi',2,15),)*2,
                        (struct.pack('<B2xi',0,99),)*2,
                        (struct.pack('<B2xi',1,15), struct.pack('<B2xi',0,15))):
            memory,_=self.memory()
            it=iter(samples)
            memory.read_process_memory=lambda *args: next(it)
            self.assertIsNone(read_native_match_scene(memory))

    def test_fallback_distinguishes_slow_celebration_from_gameplay(self):
        progress=GoalClockProgress(required_hits=3,sample_seconds=.5,minimum_rate=6)
        for second in range(60):
            self.assertFalse(progress.observe(100+second,float(second)))
        progress.reset()
        self.assertFalse(progress.observe(100,0))
        self.assertFalse(progress.observe(104,.5))
        self.assertFalse(progress.observe(108,1))
        self.assertTrue(progress.observe(112,1.5))
