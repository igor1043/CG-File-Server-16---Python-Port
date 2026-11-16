from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from server16_py import file_tools


class Server16AssetPermissionTests(unittest.TestCase):
    def test_write_access_does_not_require_changing_acl(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)
            with patch.object(file_tools.subprocess, 'run', side_effect=AssertionError('no ACL tools')):
                self.assertTrue(file_tools.ensure_server16_asset_access(target))
            self.assertEqual(list(target.iterdir()), [])

    def test_real_write_denial_reports_path_without_requesting_elevation(self):
        with tempfile.TemporaryDirectory() as temporary:
            messages=[]
            with patch.object(file_tools.tempfile, 'TemporaryFile', side_effect=PermissionError('denied')), patch.object(file_tools.subprocess, 'run') as run:
                self.assertFalse(file_tools.ensure_server16_asset_access(temporary, log=lambda *args:messages.append(args)))
                run.assert_not_called()
            self.assertIn(temporary, messages[0][0])

    def test_net_setup_copies_without_mutating_directory_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'Nets';source.mkdir()
            (source/'netcolor_0_textures.rx3').write_bytes(b'net')
            with patch.object(file_tools, 'ensure_server16_asset_access', side_effect=AssertionError('no ACL preparation')):
                file_tools.extra_setup(source, root/'goalnet', '0', 'netcolor', '0')
            self.assertEqual((root/'goalnet/netcolor_0_textures.rx3').read_bytes(), b'net')


if __name__=='__main__':unittest.main()
