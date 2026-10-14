"""Integration checks on temporary media; never writes into FIFA."""
import queue
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import ctypes

from conversor import Converter, FFMPEG, HIDDEN


class ConversionTests(unittest.TestCase):
    def test_native_drop_delivers_unicode_path(self):
        app = Converter()
        app.withdraw()
        try:
            path = r'C:\Vídeos\abertura teste.mp4'
            data = (ctypes.c_uint32*5)(20, 0, 0, 0, 1)
            payload = bytes(data) + (path+'\0\0').encode('utf-16le')
            kernel = ctypes.WinDLL('kernel32')
            kernel.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
            kernel.GlobalAlloc.restype = ctypes.c_void_p
            kernel.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel.GlobalLock.restype = ctypes.c_void_p
            kernel.GlobalUnlock.argtypes = [ctypes.c_void_p]
            memory = kernel.GlobalAlloc(0x42, len(payload))
            pointer = kernel.GlobalLock(memory)
            ctypes.memmove(pointer, payload, len(payload))
            kernel.GlobalUnlock(memory)
            app.drop.callback(app.winfo_id(), 0x233, memory, 0)
            self.assertEqual(app.events.get_nowait(), ('drop', [path]))
        finally:
            app.close()

    def test_encode_validate_publish_and_backup(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root/'input.mp4'
            subprocess.run([str(FFMPEG), '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc=size=320x180:rate=30', '-t', '0.5', '-pix_fmt',
                            'yuv420p', '-c:v', 'libx264', str(source)],
                           check=True, creationflags=HIDDEN)
            output = root/'destination'
            output.mkdir()
            previous = output/'bootflowoutro.vp8'
            previous.write_bytes(b'previous file retained')
            bumper = root/'bumper.big'
            bumper.write_bytes(b'compatible existing bumper')
            app = Converter.__new__(Converter)
            app.events = queue.Queue()
            app.cancel_event = threading.Event()
            app.log_lines = []
            app.convert(source, output, bumper, '8M')
            events = list(app.events.queue)
            self.assertTrue(any(kind == 'done' for kind, _ in events), events)
            self.assertTrue(previous.stat().st_size > 100)
            backup = next((output/'backups-conversor').rglob('bootflowoutro.vp8'))
            self.assertEqual(backup.read_bytes(), b'previous file retained')
            self.assertEqual((output/'bumper.big').read_bytes(), bumper.read_bytes())
            self.assertFalse(list(output.glob('.conversor-*')))

    def test_invalid_video_preserves_existing_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            source = root/'broken.mp4'
            source.write_bytes(b'not a video')
            previous = root/'bootflowoutro.vp8'
            previous.write_bytes(b'original')
            app = Converter.__new__(Converter)
            app.events = queue.Queue()
            app.cancel_event = threading.Event()
            app.log_lines = []
            app.convert(source, root, None, '8M')
            self.assertTrue(any(k == 'error' for k, _ in app.events.queue))
            self.assertEqual(previous.read_bytes(), b'original')
            self.assertFalse(list(root.glob('.conversor-*')))


if __name__ == '__main__':
    unittest.main()
