"""Real Windows ACL regressions for the legacy fx/glare destinations."""
import ctypes
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import win32api
import win32con
import win32security as security
from server16_py import asset_access, file_tools


@unittest.skipUnless(os.name=='nt', 'Windows ACL integration')
class InheritedStadiumAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.original=security.GetNamedSecurityInfo(str(self.root),1,4).GetSecurityDescriptorDacl()
        token=security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:self.sid=security.ConvertSidToStringSid(security.GetTokenInformation(token,security.TokenUser)[0])
        finally:token.Close()
        self.assertFalse(ctypes.windll.shell32.IsUserAnAdmin(), 'Tests must run without elevation')
        self.set_acl(self.root, f'D:P(A;OICI;0x1301bf;;;{self.sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)')

    def tearDown(self):
        # Undo only the permissions on this test's private temporary tree.
        paths=[self.root,*self.root.rglob('*')]
        for p in paths:
            self.assertTrue(p.resolve().is_relative_to(self.root))
            security.SetNamedSecurityInfo(str(p),1,4|0x20000000,None,None,self.original,None)
        self.temp.cleanup()

    def set_acl(self,path,sddl):
        sd=security.ConvertStringSecurityDescriptorToSecurityDescriptor(sddl,1)
        security.SetNamedSecurityInfo(str(path),1,ctypes.c_int32(4|0x80000000).value,None,None,sd.GetSecurityDescriptorDacl(),None)

    def info(self,path):return security.GetNamedSecurityInfo(str(path),1,7)
    def protected(self,path):return bool(self.info(path).GetSecurityDescriptorControl()[0]&0x1000)
    def legacy(self,path):self.set_acl(path,'D:P(A;;FRWD;;;OW)(A;;FA;;;SY)(A;;FA;;;BA)')
    def put(self,rel,data):
        p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p

    def test_replaces_protected_glare_file_with_an_ordinary_user(self):
        source=self.put('pack/day.rx3', b'new glare texture')
        target=self.put('data/sceneassets/fx/glares_176_3_3.rx3', b'old glare')
        self.legacy(target)
        with self.assertRaises(PermissionError):
            with target.open('wb'):pass
        self.assertTrue(file_tools._copy_file_if_needed(source,target))
        self.assertEqual(target.read_bytes(),source.read_bytes())
        self.assertFalse(self.protected(target))

    def test_moves_protected_glare_to_recovery_without_elevation(self):
        target=self.put('fx/glares_261_3_3.rx3', b'previous texture')
        previous=self.root/'recovery/glares_261_3_3.rx3';previous.parent.mkdir()
        self.legacy(target)
        with self.assertRaises(PermissionError):os.replace(target,previous)
        file_tools.replace_asset_file(target,previous,source_owned=True)
        self.assertEqual(previous.read_bytes(),b'previous texture')
        self.assertFalse(target.exists())

    def test_reopens_inheritance_when_fx_folder_denies_creating_a_file(self):
        source=self.put('pack/source.rx3',b'new glare')
        fx=self.root/'fx';fx.mkdir();self.legacy(fx)
        with self.assertRaises(PermissionError):(fx/'blocked').write_bytes(b'x')
        file_tools.copy_asset_file(source,fx/'glares_176_1_0.rx3')
        self.assertEqual((fx/'glares_176_1_0.rx3').read_bytes(),b'new glare')
        self.assertFalse(self.protected(fx))

    def test_preparation_covers_fx_and_only_the_two_owned_slots(self):
        owned=self.put('sceneassets/fx/glares_176_3_3.rx3',b'owned')
        unrelated=self.put('sceneassets/fx/glares_123_3_3.rx3',b'other stadium')
        self.legacy(owned);self.legacy(unrelated)
        file_tools.ensure_server16_stadium_access(self.root/'sceneassets')
        self.assertFalse(self.protected(owned))
        self.assertTrue(self.protected(unrelated))
        self.assertEqual(unrelated.read_bytes(),b'other stadium')

    def test_preserves_explicit_rules_owner_and_payload(self):
        target=self.put('fx/glares_176_3_3.rx3',b'unchanged')
        self.set_acl(target,'D:P(D;;0x4;;;OW)(A;;FRWD;;;OW)(A;;FA;;;SY)(A;;FA;;;BA)')
        before=self.info(target)
        def explicit(sd):
            acl=sd.GetSecurityDescriptorDacl()
            return [acl.GetAce(i) for i in range(acl.GetAceCount()) if not acl.GetAce(i)[0][1]&16]
        self.assertTrue(asset_access.restore_asset_inheritance(target))
        after=self.info(target)
        self.assertEqual(before.GetSecurityDescriptorOwner(),after.GetSecurityDescriptorOwner())
        self.assertEqual(explicit(before),explicit(after))
        self.assertEqual(target.read_bytes(),b'unchanged')

    def test_denied_acl_change_does_not_elevate_or_remove_restrictions(self):
        target=self.put('fx/glares_176_3_3.rx3',b'unchanged');self.legacy(target)
        api,kernel=asset_access._api()
        fake=SimpleNamespace(GetNamedSecurityInfoW=api.GetNamedSecurityInfoW,
            GetSecurityDescriptorControl=api.GetSecurityDescriptorControl,SetNamedSecurityInfoW=Mock(return_value=5))
        messages=Mock()
        with patch.object(asset_access,'_api',return_value=(fake,kernel)), patch('subprocess.Popen') as spawn:
            self.assertFalse(asset_access.restore_asset_inheritance(target,log=messages))
            spawn.assert_not_called()
        self.assertTrue(self.protected(target));self.assertEqual(target.read_bytes(),b'unchanged')
        self.assertIn('Current user cannot restore',messages.call_args[0][0])

    def test_unchanged_unprotected_asset_does_not_edit_its_acl(self):
        target=self.put('fx/glares_176_3_3.rx3',b'unchanged')
        before=security.ConvertSecurityDescriptorToStringSecurityDescriptor(self.info(target),1,7)
        self.assertFalse(asset_access.restore_asset_inheritance(target))
        self.assertEqual(security.ConvertSecurityDescriptorToStringSecurityDescriptor(self.info(target),1,7),before)

    def test_published_file_refreshes_inheritance_from_destination_instead_of_staging(self):
        staging=self.root/'staging';staging.mkdir()
        destination=self.root/'fx';destination.mkdir()
        self.set_acl(staging,f'D:P(A;OICI;0x1301bf;;;{self.sid})(A;OICI;FA;;;SY)')
        self.set_acl(destination,f'D:P(A;OICI;0x1301bf;;;{self.sid})(A;OICI;FR;;;WD)(A;OICI;FA;;;SY)')
        source=staging/'new.rx3';source.write_bytes(b'new glare')
        target=destination/'glares_176_1_0.rx3';os.replace(source,target)
        def inherited_sids(path):
            acl=self.info(path).GetSecurityDescriptorDacl()
            return [security.ConvertSidToStringSid(acl.GetAce(i)[2]) for i in range(acl.GetAceCount()) if acl.GetAce(i)[0][1]&16]
        self.assertNotIn('S-1-1-0',inherited_sids(target))
        self.assertTrue(asset_access.restore_asset_inheritance(target,refresh=True))
        self.assertIn('S-1-1-0',inherited_sids(target))
        self.assertEqual(target.read_bytes(),b'new glare')


if __name__=='__main__':unittest.main()
