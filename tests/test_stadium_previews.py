from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from server16_py.file_tools import discover_stadium_names, resolve_stadium_preview_path


class StadiumPreviewTests(unittest.TestCase):
    def test_resolves_and_discovers_jpeg_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            stadium_gbd = Path(temporary)
            preview_dir = stadium_gbd / "render" / "thumbnail" / "stadium"
            preview_dir.mkdir(parents=True)
            preview = preview_dir / "BRA - Maracana - Flamengo.JPG"
            Image.new("RGB", (4, 4), (20, 40, 60)).save(preview, format="JPEG")

            resolved = resolve_stadium_preview_path(stadium_gbd, "BRA - Maracana - Flamengo")
            self.assertEqual(resolved, preview)
            with Image.open(resolved) as image:
                image.load()
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, (4, 4))
            self.assertIn("BRA - Maracana - Flamengo", discover_stadium_names(stadium_gbd))

    def test_does_not_discover_or_resolve_dds_stadiums(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            folder=root/'render'/'thumbnail'/'stadium'
            folder.mkdir(parents=True)
            (folder/'DDS only.dds').write_bytes(b'DDS ')
            self.assertIsNone(resolve_stadium_preview_path(root,'DDS only'))
            self.assertNotIn('DDS only',discover_stadium_names(root))


if __name__ == "__main__":
    unittest.main()
