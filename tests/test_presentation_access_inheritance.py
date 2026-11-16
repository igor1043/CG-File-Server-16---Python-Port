"""Ordinary-user Windows regressions for scoreboard overlay destinations."""
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import win32security as security
from server16_py import asset_access, file_tools
from test_stadium_access_inheritance import InheritedStadiumAccessTests as Fixture


@unittest.skipUnless(os.name == 'nt', 'Windows ACL integration')
class InheritedPresentationAccessTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    set_acl = Fixture.set_acl
    info = Fixture.info
    protected = Fixture.protected
    legacy = Fixture.legacy
    put = Fixture.put

    def test_identical_overlay_9001_is_deletable_after_preparation_without_elevation(self):
        source = self.put('pack/game/overlays/overlay_9001.big', b'identical scoreboard')
        target = self.put('data/ui/game/overlays/overlay_9001.big', source.read_bytes())
        os.utime(target, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
        self.legacy(target)
        owner = self.info(target).GetSecurityDescriptorOwner()
        with self.assertRaises(PermissionError):
            target.unlink()
        file_tools.prepare_asset_copy(self.root/'pack', self.root/'data/ui')
        self.assertFalse(file_tools._copy_file_if_needed(source, target))
        self.assertEqual(self.info(target).GetSecurityDescriptorOwner(), owner)
        self.assertFalse(self.protected(target))
        target.unlink()

    def test_locked_overlay_and_component_folders_accept_real_replacements(self):
        a = self.put('pack/game/overlays/overlay_9001.big', b'new overlay')
        b = self.put('pack/game/globalcomponents/overlaycomponents_9/component.big', b'new component')
        target = self.put('data/ui/game/overlays/overlay_9001.big', b'old overlay')
        component = self.put('data/ui/game/globalcomponents/overlaycomponents_9/component.big', b'old component')
        for p in [target, component, target.parent, component.parent]:
            self.legacy(p)
        file_tools.prepare_asset_copy(self.root/'pack', self.root/'data/ui')
        file_tools.copy(self.root/'pack', self.root/'data/ui')
        self.assertEqual(target.read_bytes(), a.read_bytes())
        self.assertEqual(component.read_bytes(), b.read_bytes())

    def test_other_overlay_outside_package_is_untouched(self):
        self.put('pack/game/overlays/overlay_9001.big', b'new')
        one = self.put('data/ui/game/overlays/overlay_9001.big', b'old')
        other = self.put('data/ui/game/overlays/overlay_7777.big', b'other mod')
        self.legacy(one);self.legacy(other)
        before = security.ConvertSecurityDescriptorToStringSecurityDescriptor(self.info(other), 1, 7)
        file_tools.prepare_asset_copy(self.root/'pack', self.root/'data/ui')
        after = security.ConvertSecurityDescriptorToStringSecurityDescriptor(self.info(other), 1, 7)
        self.assertEqual(before, after)
        self.assertEqual(other.read_bytes(), b'other mod')
        self.assertFalse(self.protected(one))

    def test_actual_policy_denial_does_not_spawn_elevation_or_discard_original(self):
        self.put('pack/game/overlays/overlay_9001.big', b'new')
        target = self.put('data/ui/game/overlays/overlay_9001.big', b'original')
        self.legacy(target)
        api,kernel = asset_access._api()
        denied = SimpleNamespace(GetNamedSecurityInfoW=api.GetNamedSecurityInfoW,
            GetSecurityDescriptorControl=api.GetSecurityDescriptorControl,
            SetNamedSecurityInfoW=Mock(return_value=5))
        with patch.object(asset_access, '_api', return_value=(denied,kernel)), patch('subprocess.Popen') as spawn:
            file_tools.prepare_asset_copy(self.root/'pack', self.root/'data/ui')
            with self.assertRaises(PermissionError):
                file_tools.copy(self.root/'pack', self.root/'data/ui')
            spawn.assert_not_called()
        self.assertEqual(target.read_bytes(), b'original')
        self.assertTrue(self.protected(target))


del Fixture
