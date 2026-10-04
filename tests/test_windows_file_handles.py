from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from server16_py.windows_file_handles import find_exact_open_disk_path


@unittest.skipUnless(os.name == "nt", "Windows-only handle inspection")
class WindowsFileHandleTests(unittest.TestCase):
    def test_finds_only_an_exact_disk_path_open_by_the_target_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "DATA"
            other = root / "INDEX"
            target.write_bytes(b"save")
            other.write_bytes(b"index")
            with target.open("rb"):
                found = find_exact_open_disk_path(os.getpid(), [other, target])
            self.assertEqual(found, str(target.resolve()))


if __name__ == "__main__":
    unittest.main()
