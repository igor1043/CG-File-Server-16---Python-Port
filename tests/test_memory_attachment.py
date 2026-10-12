import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py.memory_access import Memory


class MemoryAttachmentTests(unittest.TestCase):
    def memory(self):
        memory = Memory()
        memory.kernel32 = Mock()
        memory.process_handle = 123
        memory.process_id = 10
        memory.base_module = 0x140000000
        memory._get_base_address = Mock(return_value=0x140000000)
        self.addCleanup(memory.close)
        return memory

    def process(self, pid):
        return SimpleNamespace(info={'pid': pid, 'name': 'fifa16.exe', 'exe': 'fifa16.exe'})

    def test_poll_keeps_connection_available_to_stadium_worker(self):
        memory = self.memory()
        with patch('psutil.process_iter', return_value=[self.process(10)]):
            for _ in range(20):
                self.assertTrue(memory.attack('fifa16'))
                self.assertTrue(memory.is_open())
        memory.kernel32.CloseHandle.assert_not_called()
        memory.kernel32.OpenProcess.assert_not_called()
        self.assertEqual(memory.process_handle, 123)

    def test_new_process_replaces_previous_connection(self):
        memory = self.memory()
        memory.kernel32.OpenProcess.return_value = 456
        with patch('psutil.process_iter', return_value=[self.process(11)]):
            self.assertTrue(memory.attack('fifa16'))
        memory.kernel32.CloseHandle.assert_called_once_with(123)
        self.assertEqual(memory.process_id, 11)
        self.assertEqual(memory.process_handle, 456)

    def test_process_exit_closes_connection(self):
        memory = self.memory()
        with patch('psutil.process_iter', return_value=[]):
            self.assertFalse(memory.attack('fifa16'))
        self.assertFalse(memory.is_open())
        memory.kernel32.CloseHandle.assert_called_once_with(123)

    def test_module_base_is_retried_after_early_startup(self):
        memory = self.memory()
        memory.base_module = 0
        memory._get_base_address.side_effect = [0, 0x140000000]
        with patch('psutil.process_iter', return_value=[self.process(10)]):
            self.assertFalse(memory.attack('fifa16'))
            self.assertFalse(memory.is_open())
            self.assertTrue(memory.attack('fifa16'))
            self.assertTrue(memory.is_open())
        memory.kernel32.CloseHandle.assert_not_called()
        memory.kernel32.OpenProcess.assert_not_called()

    def test_close_clears_previous_game_address(self):
        memory = self.memory()
        memory.close()
        self.assertEqual(memory.base_module, 0)
        self.assertEqual(memory.process_id, 0)
