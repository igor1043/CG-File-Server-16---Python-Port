from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server16_py import file_tools


class Server16AssetPermissionTests(unittest.TestCase):
    def test_repairs_only_the_requested_tree_and_adds_current_user_modify(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "goalnet"
            target.mkdir()
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            with (
                patch.object(file_tools.os, "name", "nt"),
                patch.object(file_tools, "_current_windows_user_sid", return_value="S-1-5-21-1000"),
                patch.object(file_tools.subprocess, "run", side_effect=fake_run),
            ):
                self.assertTrue(file_tools.ensure_server16_asset_access(target))

            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][1], str(target))
            self.assertIn("/inheritance:e", calls[0])
            self.assertIn("/T", calls[0])
            self.assertEqual(calls[1][1], str(target))
            self.assertIn("*S-1-5-21-1000:(OI)(CI)(M)", calls[1])
            self.assertNotIn("/T", calls[1])
            self.assertNotIn("/reset", calls[0] + calls[1])
            self.assertNotIn("/takeown", calls[0] + calls[1])

    def test_non_windows_is_a_noop(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "goalnet"
            target.mkdir()
            with (
                patch.object(file_tools.os, "name", "posix"),
                patch.object(file_tools.subprocess, "run") as run,
            ):
                self.assertTrue(file_tools.ensure_server16_asset_access(target))
                run.assert_not_called()

    def test_net_setup_repairs_only_its_destination_before_copying(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "FSW" / "Nets"
            destination = root / "data" / "sceneassets" / "goalnet"
            source.mkdir(parents=True)
            (source / "netcolor_0_textures.rx3").write_bytes(b"net")
            calls = []
            original_copy = file_tools._copy_file_if_needed

            def traced_copy(src, dst):
                calls.append(("copy", Path(dst)))
                return original_copy(src, dst)

            def ensure(path, log=None):
                calls.append(("acl", Path(path)))
                return True

            with (
                patch.object(file_tools, "ensure_server16_asset_access", side_effect=ensure),
                patch.object(file_tools, "_copy_file_if_needed", side_effect=traced_copy),
            ):
                file_tools.extra_setup(source, destination, "0", "netcolor", "0")

            self.assertEqual(calls[0], ("acl", destination))
            self.assertEqual(calls[1][0], "copy")
            self.assertEqual(calls[1][1], destination / "netcolor_0_textures.rx3")


if __name__ == "__main__":
    unittest.main()
