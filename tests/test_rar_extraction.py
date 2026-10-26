from __future__ import annotations

import os
import errno
import queue
import subprocess
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server16_py import file_tools
from server16_py.entrance_runtime import TeamEntranceRuntime
from server16_py.stadium_runtime import StadiumRuntime


class RarExtractionTests(unittest.TestCase):
    DATA = b'complete model payload'

    def fake_module(self, name='BRA - Stadium/model.rx3', crc=None, texture=False):
        data = self.DATA
        member = SimpleNamespace(filename=name, file_size=len(data),
            CRC=zlib.crc32(data) if crc is None else crc, isdir=lambda:False)
        members = [member]
        if texture:
            members.append(SimpleNamespace(filename='BRA - Stadium/texture_day.rx3',
                file_size=len(data), CRC=zlib.crc32(data), isdir=lambda:False))
        class Reader:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def infolist(self): return members
        return SimpleNamespace(RarFile=lambda *args:Reader())

    def extract(self, root, run, tools=None, module=None, **options):
        output = root/'output'
        archive = root/'stadium.rar'; archive.touch()
        with patch.object(file_tools,'_rarmod',module or self.fake_module()), \
             patch.object(file_tools,'_rar_extractors',return_value=tools or [('UnRAR','fake-unrar')]), \
             patch.object(file_tools.subprocess,'run',side_effect=run):
            return file_tools.extract_archive(archive,output,**options)

    def fake_success(self,command,**kwargs):
        stage=Path(command[-1]); target=stage/'BRA - Stadium'/'model.rx3'
        target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(self.DATA)
        self.assertNotIn('--to-stdout',command)
        return SimpleNamespace(returncode=0,stdout='',stderr='')

    def test_full_archive_checked_before_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            self.assertEqual(self.extract(root,self.fake_success),'UnRAR')
            self.assertEqual((root/'output'/'BRA - Stadium'/'model.rx3').read_bytes(),self.DATA)
            self.assertEqual(list(root.glob('rar_stage_*')),[])

    def test_failed_backend_isolated_and_tar_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); calls=[]
            def run(command,**kwargs):
                calls.append(command)
                if len(calls)==1:
                    (Path(command[-1])/'incomplete.rx3').write_bytes(b'partial')
                    return SimpleNamespace(returncode=2,stdout='',stderr='broken pipe')
                return self.fake_success(command,**kwargs)
            self.assertEqual(self.extract(root,run,[('UnRAR','fake-unrar'),('tar','fake-tar')]),'tar')
            self.assertEqual(len(calls),2)
            self.assertFalse((root/'output'/'incomplete.rx3').exists())
            self.assertNotEqual(calls[0][-1],calls[1][-1])

    def test_fast_publication_keeps_crc_validation_and_avoids_file_copies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); events=[]; original_check=file_tools._check_rar_output
            def check(*args):
                original_check(*args); events.append('validated')
            with patch.object(file_tools,'_check_rar_output',side_effect=check), \
                 patch.object(file_tools.shutil,'copy2',side_effect=AssertionError('redundant copy')):
                self.assertEqual(self.extract(root,self.fake_success,fast_publish=True,
                    publication_callback=lambda method,reason:events.append(method)),'UnRAR')
            self.assertEqual(events,['validated','rename'])
            self.assertEqual((root/'output/BRA - Stadium/model.rx3').read_bytes(),self.DATA)
            self.assertEqual(list(root.glob('rar_stage_*')),[])

    def test_rename_errors_use_legacy_copy_without_reextracting(self):
        for error in (PermissionError('antivirus lock'),OSError(errno.EXDEV,'another volume'),OSError('unsupported filesystem')):
            with self.subTest(error=error),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);calls=[];methods=[]
                def extract(command,**kwargs):
                    calls.append(command);return self.fake_success(command,**kwargs)
                with patch.object(Path,'rename',side_effect=error), \
                     patch.object(file_tools.shutil,'copy2',wraps=file_tools.shutil.copy2) as copy:
                    self.assertEqual(self.extract(root,extract,fast_publish=True,
                        publication_callback=lambda method,reason:methods.append((method,reason))),'UnRAR')
                self.assertEqual(len(calls),1)
                self.assertEqual(methods[0][0],'copy')
                self.assertIn('rename failed',methods[0][1])
                self.assertEqual(copy.call_count,1)
                self.assertEqual((root/'output/BRA - Stadium/model.rx3').read_bytes(),self.DATA)
                self.assertEqual(list(root.glob('rar_stage_*')),[])

    def test_default_and_populated_destination_keep_original_copy_path(self):
        for fast in (False,True):
            with self.subTest(fast=fast),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                if fast:
                    output=root/'output';output.mkdir();(output/'preserve.txt').write_bytes(b'keep me')
                methods=[]
                with patch.object(Path,'rename',side_effect=AssertionError('must not move existing content')):
                    self.extract(root,self.fake_success,fast_publish=fast,
                        publication_callback=lambda method,reason:methods.append(method))
                self.assertEqual(methods,['copy'])
                self.assertEqual((root/'output/BRA - Stadium/model.rx3').read_bytes(),self.DATA)
                if fast:self.assertEqual((root/'output/preserve.txt').read_bytes(),b'keep me')

    def test_destination_populated_or_replaced_during_extraction_is_not_removed(self):
        for replaced in (False,True):
            with self.subTest(replaced=replaced),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary); methods=[]
                def extract(command,**kwargs):
                    result=self.fake_success(command,**kwargs)
                    output=root/'output'
                    if replaced:
                        os.rename(output,root/'original_directory');output.mkdir()
                    (output/'arrived_later.txt').write_bytes(b'preserve concurrent content')
                    return result
                with patch.object(Path,'rename',side_effect=AssertionError('must not rename changed destination')):
                    self.extract(root,extract,fast_publish=True,
                        publication_callback=lambda method,reason:methods.append(method))
                self.assertEqual(methods,['copy'])
                self.assertEqual((root/'output/arrived_later.txt').read_bytes(),b'preserve concurrent content')

    def test_corrupt_or_incomplete_data_never_reaches_fast_or_legacy_publication(self):
        for crc in (123,zlib.crc32(self.DATA)):
            with self.subTest(crc=crc),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                def extract(command,**kwargs):
                    result=self.fake_success(command,**kwargs)
                    if crc!=123:(Path(command[-1])/'BRA - Stadium/model.rx3').write_bytes(b'partial')
                    return result
                with patch.object(Path,'rename',side_effect=AssertionError('invalid data cannot move')), \
                     patch.object(file_tools.shutil,'copy2',side_effect=AssertionError('invalid data cannot copy')):
                    with self.assertRaises(RuntimeError):
                        self.extract(root,extract,module=self.fake_module(crc=crc),fast_publish=True)
                self.assertEqual(list((root/'output').iterdir()),[])
                self.assertEqual(list(root.glob('rar_stage_*')),[])

    def test_replaced_empty_destination_keeps_original_copy_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);methods=[]
            def extract(command,**kwargs):
                result=self.fake_success(command,**kwargs)
                os.rename(root/'output',root/'original_directory')
                (root/'output').mkdir()
                return result
            with patch.object(Path,'rename',side_effect=AssertionError('destination identity changed')):
                self.extract(root,extract,fast_publish=True,
                    publication_callback=lambda method,reason:methods.append(method))
            self.assertEqual(methods,['copy'])
            self.assertTrue((root/'original_directory').is_dir())
            self.assertEqual((root/'output/BRA - Stadium/model.rx3').read_bytes(),self.DATA)

    def test_locked_empty_destination_keeps_original_copy_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);methods=[];original_rmdir=Path.rmdir
            def rmdir(path):
                if path==root/'output':raise PermissionError('directory locked')
                return original_rmdir(path)
            with patch.object(Path,'rmdir',autospec=True,side_effect=rmdir), \
                 patch.object(Path,'rename',side_effect=AssertionError('directory cannot be removed')):
                self.extract(root,self.fake_success,fast_publish=True,
                    publication_callback=lambda method,reason:methods.append((method,reason)))
            self.assertEqual(methods[0][0],'copy')
            self.assertIn('fast publication unavailable',methods[0][1])
            self.assertEqual((root/'output/BRA - Stadium/model.rx3').read_bytes(),self.DATA)

    def test_filesystem_without_stable_identity_keeps_original_copy_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);methods=[]
            with patch.object(file_tools,'_directory_identity',return_value=None), \
                 patch.object(Path,'rename',side_effect=AssertionError('file identity unavailable')):
                self.extract(root,self.fake_success,fast_publish=True,
                    publication_callback=lambda method,reason:methods.append(method))
            self.assertEqual(methods,['copy'])
            self.assertEqual((root/'output/BRA - Stadium/model.rx3').read_bytes(),self.DATA)

    def test_missing_manifest_keeps_legacy_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); archive=root/'stadium.rar';archive.touch();methods=[]
            with patch.object(file_tools,'_rarmod',None), \
                 patch.object(file_tools,'_rar_extractors',return_value=[('UnRAR','fake-unrar')]), \
                 patch.object(file_tools.subprocess,'run',side_effect=self.fake_success), \
                 patch.object(Path,'rename',side_effect=AssertionError('manifest is required')):
                file_tools.extract_archive(archive,root/'output',fast_publish=True,
                    publication_callback=lambda method,reason:methods.append(method))
            self.assertEqual(methods,['copy'])
            self.assertEqual((root/'output/BRA - Stadium/model.rx3').read_bytes(),self.DATA)

    def test_failed_fallback_reports_error_instead_of_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);reports=[]
            with patch.object(Path,'rename',side_effect=PermissionError('locked')), \
                 patch.object(file_tools.shutil,'copy2',side_effect=OSError('disk full')):
                with self.assertRaisesRegex(OSError,'disk full'):
                    self.extract(root,self.fake_success,fast_publish=True,
                        publication_callback=lambda method,reason:reports.append(method))
            self.assertEqual(reports,[])
            self.assertEqual(list(root.glob('rar_stage_*')),[])

    def test_diagnostic_failure_does_not_invalidate_complete_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def fail(*args):raise RuntimeError('log unavailable')
            self.extract(root,self.fake_success,fast_publish=True,publication_callback=fail)
            self.assertEqual((root/'output/BRA - Stadium/model.rx3').read_bytes(),self.DATA)

    def test_link_or_reparse_file_is_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'safe.rx3';source.write_bytes(self.DATA)
            original_lstat=Path.lstat
            def reparse(path):
                info=original_lstat(path)
                return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=1024) if path==source else info
            with patch.object(Path,'lstat',autospec=True,side_effect=reparse):
                with self.assertRaisesRegex(RuntimeError,'link not allowed'):
                    file_tools._rar_publication_paths(root)

    def stadium_app(self,root):
        packages=root/'packages';packages.mkdir();(packages/'BRA - Stadium.rar').touch()
        game=root/'game'
        return SimpleNamespace(base_dir=root,exedir=game,targetpath=packages,
            settings_ini=SimpleNamespace(key_exists=lambda *a:True,read=lambda *a:'BRA - Stadium,None,None,None'),
            Psource=game/'FSW/Police',Nsource=game/'FSW/Nets',PitchMowsource=game/'FSW/PitchMowPattern',
            Pdest=game/'data/sceneassets/slc',Ndest=game/'data/sceneassets/goalnet',
            PitchMowdest=game/'data/sceneassets/pitch',PoliceNum='4',Stadiumtype='first',
            Movdata=game/'data/movies/bootflowoutro.vp8',MOVBUMP=game/'data/ui/TV/bumper.big',
            log=Mock(),_worker_queue=queue.Queue())

    def test_stadium_worker_uses_fast_publication_and_handles_rename_failure(self):
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);app=self.stadium_app(root);original_rename=Path.rename
                def rename(path,target):
                    if fail:raise PermissionError('locked')
                    return original_rename(path,target)
                def extract_complete(command,**kwargs):
                    result=self.fake_success(command,**kwargs)
                    (Path(command[-1])/'BRA - Stadium/texture_day.rx3').write_bytes(self.DATA)
                    return result
                with patch.object(file_tools,'_rarmod',self.fake_module(texture=True)), \
                     patch.object(file_tools,'_rar_extractors',return_value=[('UnRAR','fake-unrar')]), \
                     patch.object(file_tools.subprocess,'run',side_effect=extract_complete), \
                     patch.object(Path,'rename',autospec=True,side_effect=rename):
                    payload=StadiumRuntime(app).run_stadium_copy_job('1043','stadium','176','BRA - Stadium')
                self.assertEqual(payload['stad_name'],'BRA - Stadium')
                self.assertEqual((app.exedir/'data/sceneassets/stadium/stadium_176.rx3').read_bytes(),self.DATA)
                method='copy' if fail else 'rename'
                self.assertTrue(any(f'Stadium extraction publication: {method};' in str(call) for call in app.log.call_args_list))
                self.assertEqual(list((root/'runtime').iterdir()),[])

    def test_invalid_archive_cannot_modify_game_assets_even_with_fast_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);app=self.stadium_app(root)
            original=app.exedir/'data/sceneassets/stadium/stadium_176.rx3'
            original.parent.mkdir(parents=True);original.write_bytes(b'original game model')
            with patch.object(file_tools,'_rarmod',self.fake_module(crc=123)), \
                 patch.object(file_tools,'_rar_extractors',return_value=[('UnRAR','fake-unrar')]), \
                 patch.object(file_tools.subprocess,'run',side_effect=self.fake_success):
                with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):
                    StadiumRuntime(app).run_stadium_copy_job('1043','stadium','176','BRA - Stadium')
            self.assertEqual(original.read_bytes(),b'original game model')
            self.assertEqual(list((root/'runtime').iterdir()),[])

    def test_crc_failure_cannot_publish_partial_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); original=root/'output'/'BRA - Stadium'/'model.rx3'
            original.parent.mkdir(parents=True); original.write_bytes(b'original')
            with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):
                self.extract(root,self.fake_success,module=self.fake_module(crc=123))
            self.assertEqual(original.read_bytes(),b'original')
            self.assertEqual(list(root.glob('rar_stage_*')),[])

    def test_short_read_cannot_publish_partial_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def run(command,**kwargs):
                result=self.fake_success(command,**kwargs)
                (Path(command[-1])/'BRA - Stadium'/'model.rx3').write_bytes(b'49 bytes')
                return result
            with self.assertRaisesRegex(RuntimeError,'Incomplete'):
                self.extract(root,run)
            self.assertEqual(list((root/'output').iterdir()),[])

    def test_timeout_no_extractor_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaisesRegex(RuntimeError,'timed out'):
                self.extract(root,lambda *args,**kwargs:(_ for _ in ()).throw(subprocess.TimeoutExpired('unrar',300)))
            for name in ('../escape.rx3','C:/escape.rx3','\\\\server/share/file.rx3'):
                with self.assertRaisesRegex(RuntimeError,'Unsafe archive'):
                    self.extract(root,self.fake_success,module=self.fake_module(name=name))
            with patch.object(file_tools,'_rar_extractors',return_value=[]),patch.object(file_tools,'_rarmod',None):
                with self.assertRaisesRegex(RuntimeError,'no RAR extractor'):
                    file_tools.extract_archive(root/'stadium.rar',root/'output')

    def test_finds_installed_winrar_even_outside_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); executable=root/'WinRAR'/'UnRAR.exe'
            executable.parent.mkdir(); executable.touch()
            with patch.dict(os.environ,{'ProgramFiles':str(root)},clear=True),patch.object(file_tools.shutil,'which',return_value=None):
                self.assertEqual(file_tools._rar_extractors(),[('UnRAR',str(executable))])

    def test_zip_still_supported_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); archive=root/'stadium.zip'
            with zipfile.ZipFile(archive,'w') as zip_file:
                zip_file.writestr('Stadium/model.rx3',self.DATA)
            self.assertEqual(file_tools.extract_archive(archive,root/'zip_output'),'ZIP')
            with zipfile.ZipFile(archive,'w') as zip_file:
                zip_file.writestr('../escape.rx3',self.DATA)
            with self.assertRaisesRegex(RuntimeError,'Unsafe archive'):
                file_tools.extract_archive(archive,root/'zip_bad')

    def test_entrance_menu_without_team_never_indexes_empty_tokens(self):
        for team in ('',' ', '0','4294967295'):
            runtime=TeamEntranceRuntime(SimpleNamespace(HID=team,module_enabled=lambda name:True))
            self.assertFalse(runtime.start_for_match())


if __name__=='__main__':
    unittest.main()
