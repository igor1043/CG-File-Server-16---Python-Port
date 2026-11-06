import json
import ast
import os
from pathlib import Path
import tempfile
import threading
import time
import subprocess
import unittest
from unittest.mock import patch, Mock

from server16_py import cache_maintenance as cache


class CacheMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'game'
        for name in ('ModCarrerMode/data','data/sceneassets','runtime'):(self.root/name).mkdir(parents=True,exist_ok=True)
    def file(self,relative,body=b'generated',root=None):
        p=(root or self.root)/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
        os.utime(p,(time.time()-10,time.time()-10));return p
    def clean(self,**kwargs):
        return cache.maintain(self.root,guard=lambda:False,record=False,**kwargs)
    def test_career_and_finance_state_cannot_become_cache(self):
        preserved=[self.file(p) for p in (
            cache.MARKET+'league_days/12/20260101.tsv',cache.MARKET+'save_events/write.tsv',
            cache.MARKET+'state_ready.json','ModCarrerMode/data/manager_market/catalog.sqlite3',
            'runtime/settings.json','ModCarrerMode/runtime/club_environment/room/room_v3.py',
            'ModCarrerMode/runtime/club_environment/room/v3-settings/1043_finish.txt',
            'runtime/server16_stadium_apply_abc/previous/data/sceneassets/stadium.rx3',
            'ModCarrerMode/cache/club_browser/coach/'+'a'*64+'/important.sqlite3-wal')]
        old=self.file(cache.MARKET+'packages/managers_'+'a'*64+'.big')
        report=self.clean();self.assertFalse(old.exists());self.assertEqual(report.files,1)
        self.assertTrue(all(p.read_bytes()==b'generated' for p in preserved))
    def test_budget_keeps_latest_art_and_template_pair(self):
        art=[];templates=[]
        for i in range(3):
            key=str(i)*64
            p=self.file(cache.MARKET+'artwork_cache/art_'+key+'.zip');os.utime(p,(100+i,100+i));art.append(p)
            p=self.file(cache.MARKET+'native_templates/template_'+key+'.big');os.utime(p,(100+i,100+i));templates.append(p)
            self.file(str(p.relative_to(self.root).with_suffix('.json')))
        self.clean()
        self.assertEqual([p.exists() for p in art],[False,False,True])
        self.assertEqual([p.exists() for p in templates],[False,False,True])
        self.assertTrue(templates[-1].with_suffix('.json').exists())
        self.assertFalse(templates[0].with_suffix('.json').exists())
    def test_missing_policy_or_descriptor_keeps_room(self):
        p=self.file(cache.ROOM+'shared/coach_panels_1043_'+'a'*18+'_r76.rx3')
        with patch.object(cache,'policy_assets',return_value=None):self.clean()
        self.assertTrue(p.exists())
        with patch.object(cache,'policy_assets',return_value=set()):self.clean()
        self.assertTrue(p.exists())
    def test_room_preserves_distribution_current_and_unknown_assets(self):
        names=['shared/coach_panels_1043_'+k*18+'_r76.rx3' for k in 'abc']
        current,shipped,stale=[self.file(cache.ROOM+n) for n in names]
        static=self.file(cache.ROOM+'shared/locker_support_r68.rx3')
        original=self.file(cache.ROOM+'room_roles_'+'f'*14+'.rx3')
        self.file(cache.ROOM+'manifest.json',json.dumps(dict(model_files={'room_roles.rx3':original.name})).encode())
        self.file('ModCarrerMode/runtime/club_environment/room/runtime/native_components_v2.txt',
                  ('S16NATIVE 3\n"'+current.relative_to(self.root).as_posix()+'"\n').encode())
        with patch.object(cache,'policy_assets',return_value={shipped.relative_to(self.root).as_posix()}):self.clean()
        self.assertFalse(stale.exists());self.assertTrue(all(p.exists() for p in (current,shipped,static,original)))
    def test_any_running_game_defers_all_removals(self):
        p=self.file(cache.MARKET+'packages/managers_'+'a'*64+'.big')
        report=cache.maintain(self.root,guard=lambda:True,record=False)
        self.assertTrue(report.deferred);self.assertTrue(p.exists());self.assertEqual(report.files,0)
    def test_game_start_during_sweep_stops_without_touching_remaining_files(self):
        paths=[self.file(cache.MARKET+'packages/managers_'+c*64+'.big') for c in 'abc']
        def guard():return any(not p.exists() for p in paths)
        report=cache.maintain(self.root,guard=guard,record=False)
        self.assertTrue(report.deferred);self.assertEqual(sum(p.exists() for p in paths),2)
    def test_hardlink_bytes_count_only_the_last_name(self):
        a=self.file('data/sceneassets/server16_club_xi/1/a/atlas.rx3',b'x'*600)
        b=a.parent/'copy.rx3';os.link(a,b)
        report=self.clean();self.assertEqual(report.files,2);self.assertEqual(report.logical_bytes,1200);self.assertEqual(report.released_bytes,600)
    def test_cache_hardlink_to_original_does_not_modify_original(self):
        original=self.file('data/sceneassets/original.rx3',b'original')
        path=self.root/'data/sceneassets/server16_club_xi/1/a/atlas.rx3';path.parent.mkdir(parents=True)
        os.link(original,path);report=self.clean()
        self.assertFalse(path.exists());self.assertEqual(original.read_bytes(),b'original');self.assertEqual(report.released_bytes,0)
    def test_directory_junction_and_file_link_are_not_traversed(self):
        outside=Path(self.temp.name)/'outside';outside.mkdir();p=outside/'atlas.rx3';p.write_bytes(b'original')
        parent=self.root/'data/sceneassets/server16_club_xi';parent.mkdir(parents=True)
        link=parent/'99'
        try:os.symlink(outside,link,target_is_directory=True)
        except OSError:
            if os.name!='nt':self.skipTest('Symlink creation unavailable')
            created=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
            if created.returncode:self.skipTest('Junction creation unavailable')
        self.addCleanup(lambda:os.rmdir(link) if link.exists() else None)
        self.clean();self.assertEqual(p.read_bytes(),b'original');self.assertTrue((parent/'99').is_dir())
    def test_unknown_root_has_no_cleanup_scope(self):
        p=self.file('runtime/server16_stad_abc/atlas.rx3',root=Path(self.temp.name)/'unknown')
        result=cache.maintain(p.parents[2],guard=lambda:False,record=False)
        self.assertEqual(result.files,0);self.assertTrue(p.exists())
    def test_frontend_without_original_is_preserved(self):
        key='a'*24;p=self.file('data/sceneassets/server16_frontend/'+key+'/model.rx3')
        self.file(str(p.parent.relative_to(self.root))+'/ready.json',json.dumps(dict(source=str(self.root/'missing.rar'))).encode())
        self.clean();self.assertTrue(p.exists())
    def test_match_route_invalidated_before_immutable_assets_removed(self):
        p=self.file('data/sceneassets/server16_match/'+'a'*32+'/model.rx3')
        route=self.file('data/fifarna/lua/assets/server16_match_176.lua',b'old route')
        self.clean();self.assertFalse(p.exists());self.assertIn('= nil',route.read_text())
    def test_locked_path_is_quarantined_but_not_counted_as_freed(self):
        p=self.file(cache.MARKET+'packages/managers_'+'a'*64+'.big',b'tmp')
        original=Path.unlink
        def unlink(path,*a,**kw):
            if path==p:raise PermissionError('in use')
            return original(path,*a,**kw)
        with patch.object(Path,'unlink',unlink):report=self.clean()
        target=self.root.parent/('FIFA16-cache-descartavel-'+self.root.name)/p.relative_to(self.root)
        self.assertTrue(target.exists());self.assertFalse(p.exists());self.assertEqual(report.moved_bytes,3);self.assertEqual(report.released_bytes,0)
    def test_dry_run_and_second_sweep_are_idempotent(self):
        p=self.file(cache.MARKET+'packages/managers_'+'a'*64+'.big')
        report=self.clean(dry_run=True);self.assertEqual(report.files,1);self.assertTrue(p.exists())
        self.clean();self.assertEqual(self.clean().files,0)
    def test_mutex_prevents_concurrent_maintenance(self):
        with cache.RootLock(self.root):
            result=self.clean();self.assertTrue(result.deferred)
    def test_session_lifecycle_startup_active_exit_and_launch_cancel(self):
        p=self.file(cache.MARKET+'packages/managers_'+'a'*64+'.big')
        active=[True];service=cache.SessionCaches(Mock(),interval=.02,checker=lambda root:active[0])
        self.addCleanup(service.close);service.bind(self.root);time.sleep(.08);self.assertTrue(p.exists())
        active[0]=False;deadline=time.monotonic()+3
        while p.exists() and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(p.exists())
        deadline=time.monotonic()+3
        while not service.reserve_launch() and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(service.reserve_launch())
        p=self.file(cache.MARKET+'packages/managers_'+'b'*64+'.big');service.request(self.root);time.sleep(.08)
        self.assertTrue(p.exists())

    def test_plan_can_be_cancelled_before_mutating(self):
        p=self.file(cache.MARKET+'packages/managers_'+'a'*64+'.big');calls=[0]
        def guard():
            calls[0]+=1
            return calls[0]>=3
        report=cache.maintain(self.root,guard=guard,record=False)
        self.assertTrue(report.deferred);self.assertTrue(p.exists());self.assertEqual(report.files,0)

    def test_running_fifa_in_another_location_still_blocks(self):
        process=Mock();process.pid=os.getpid()+1000;process.info={'name':'FIFA16.exe','cmdline':[], 'exe':'Z:/another/FIFA16.exe'}
        with patch.object(cache.psutil,'process_iter',return_value=[process]):self.assertTrue(cache.busy(self.root))

    def test_app_launch_waits_until_sweep_releases_its_work(self):
        from types import SimpleNamespace
        source=Path(__file__).resolve().parents[1]/'server16_py/app.py'
        tree=ast.parse(source.read_text(encoding='utf8'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='launch_fifa')
        namespace={'messagebox':Mock(),'subprocess':Mock(),'Path':Path}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(source),'exec'),namespace)
        cls=type('App',(),{'launch_fifa':namespace['launch_fifa']})
        app=cls();app.fifaEXE='fifa16.exe';app._is_target_process_running=Mock(return_value=False)
        app._visual_caches=SimpleNamespace(reserve_launch=Mock(return_value=False));app.after=Mock()
        app.launch_fifa();app.after.assert_called_once_with(100,app.launch_fifa)
        namespace['subprocess'].Popen.assert_not_called()


if __name__=='__main__':unittest.main()
