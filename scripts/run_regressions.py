"""Offline release gate: isolated suites, exit codes and persistent test logs.

No FIFA attachment, native-save mutation or production DLL installation.
Python suites need the development requirements; native suites need MSVC x64.
"""
from pathlib import Path
import argparse, ast, datetime, importlib.util, json, os, subprocess, sys, time

SOURCE = Path(__file__).resolve().parents[1]
ROOT = SOURCE.parents[1]
ENVIRONMENT = SOURCE/'club_environment'
GROUPS = {
    'server': SOURCE/'tests',
    'bank': ENVIRONMENT/'bank',
    'preview': ENVIRONMENT/'preview',
    'room': ENVIRONMENT/'room',
    'trophies': ENVIRONMENT/'trophy_room',
    'market': ENVIRONMENT/'market',
    'managers': ENVIRONMENT/'manager_market',
    'browser': SOURCE/'club_browser',
    'scenes': SOURCE/'common',
    'theme': ENVIRONMENT,
}
# Retained development screens/tools, unavailable in the public build. The
# audit option still runs them and reports their failures; never count them as passed.
INACTIVE = {
 'test_narration_panel': 'NARRATION_PICKER_AVAILABLE is disabled in the public build',
 'test_narration_autosave': 'External narration authoring tools are not part of this repository',
 'test_narration_club_names': 'External narration authoring tools are not part of this repository',
 'test_narration_editor': 'External narration authoring tools are not part of this repository',
 'test_narration_generic_policy': 'External narration authoring tools are not part of this repository',
 'test_narration_library': 'External narration authoring tools are not part of this repository',
 'test_narration_portability': 'External narration authoring tools are not part of this repository',
 'test_narration_projects': 'External narration authoring tools are not part of this repository',
 'test_narration_startup': 'External narration authoring tools are not part of this repository',
}

def unit_modules(folder):
    for file in sorted(folder.glob('test_*.py')):
        tree=ast.parse(file.read_text(encoding='utf-8-sig'))
        if any(isinstance(node,ast.ClassDef) and any(
            (isinstance(base,ast.Attribute) and base.attr=='TestCase') or
            (isinstance(base,ast.Name) and base.id.endswith('TestCase')) for base in node.bases)
            for node in ast.walk(tree)):yield file.stem

def python_environment(game_root=ROOT, folder=SOURCE):
    env = dict(os.environ, SERVER16_GAME_ROOT=str(game_root), PYTHONDONTWRITEBYTECODE='1')
    env['PYTHONPATH'] = os.pathsep.join(map(str, (folder, SOURCE, ENVIRONMENT, ENVIRONMENT/'vendor',
        ENVIRONMENT/'bank', ENVIRONMENT/'preview', ENVIRONMENT/'market', ENVIRONMENT/'room',
        SOURCE/'club_browser', SOURCE/'tests', SOURCE/'vendor', ROOT/'code-release/test-deps')))
    return env


def room_collision_fixtures(output):
    """Real installed-room bounds, written only under the test report folder."""
    data=ROOT/'ModCarrerMode/data/club_environment/room/runtime'
    boxes=(json.loads((data/'room_roles_r62.json').read_text(encoding='utf8'))['obstacles']
        +json.loads((data/'medical_room_r57.json').read_text(encoding='utf8'))['obstacles'])
    spec=importlib.util.spec_from_file_location('room_collision_fixture_rules',ENVIRONMENT/'room/room_collision_r70.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    paths=[]
    for name,items in [('legacy',boxes),('corrected',module.solid_obstacles(boxes))]:
        path=output/(name+'-collision.txt')
        path.write_text(''.join(' '.join(map(str,b['lo']+b['hi']))+'\n' for b in items),encoding='utf8')
        paths.append(path)
    return paths

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', action='append', choices=(*GROUPS, 'native', 'browser-native','cinematics'))
    parser.add_argument('--output', type=Path, default=ROOT/'code-release/regressions')
    parser.add_argument('--game-root', type=Path, default=ROOT, help='Optional installed game for kit/font integration tests')
    parser.add_argument('--audit-inactive', action='store_true', help='Also run retained, disabled developer features')
    args = parser.parse_args()
    selected = args.group or [*GROUPS, 'native','cinematics']
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    rows = []; env = python_environment()
    def run(name, command, cwd=ROOT, timeout=900):
        begin = time.monotonic()
        try:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=timeout,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            code, log = result.returncode, result.stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, log = 125, str(exc).encode('utf8')
        log_path = output/(name+'.log'); log_path.write_bytes(log)
        # A discover run that imports CLI-only files without any tests is not a pass.
        if b'Ran 0 tests' in log: code = 126
        rows.append(dict(name=name, passed=code==0, exit_code=code,
            seconds=round(time.monotonic()-begin, 2), log=str(log_path)))
        print(('PASS ' if code==0 else 'FAIL ')+name, flush=True)
        (output/'results.json').write_text(json.dumps(dict(
            date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            suites=rows, inactive_features_not_validated={} if args.audit_inactive else INACTIVE,
            original_game_assets_validated=args.game_root.resolve()!=ROOT.resolve(),
            passed=all(r['passed'] for r in rows)), indent=2)+'\n', encoding='utf8')
        return code == 0
    for group in selected:
        if group in GROUPS:
            folder = GROUPS[group]
            env=python_environment(args.game_root,folder)
            modules=[name for name in unit_modules(folder) if args.audit_inactive or name not in INACTIVE]
            if group=='trophies':
                modules=['trophy_room.'+name for name in modules]
            if group=='room' and args.game_root.resolve()==ROOT.resolve():
                modules.remove('test_kit_print_r61')
                modules.append('test_kit_print_r61.KitPrint.test_absent_hotspot_cannot_fall_back_to_a_fixed_shirt_decal')
            if group=='server':
                for module in modules:run(group+'-'+module,[sys.executable,'-B','-m','unittest',module,'-v'])
            else:run(group, [sys.executable, '-B', '-m', 'unittest', *modules, '-v'])
        elif group=='cinematics':
            env=python_environment(args.game_root,SOURCE)
            env['EXTRA_SCENES_OUTPUT']=str(output/'extra-scenes-native')
            run('extra-scenes-native',['cmd','/d','/c',str(SOURCE/'scripts/build_extra_scenes.cmd')])
        elif group=='browser-native':
            if args.game_root.resolve()==ROOT.resolve():
                parser.error('browser-native requires --game-root with the original FIFA assets')
            run('browser-native', ['cmd','/d','/c','call',str(SOURCE/'club_browser/test_native.cmd'),
                str(args.game_root),str(output/'browser-native')])
            run('globe-assets', [sys.executable,'-B',str(SOURCE/'club_browser/test_globe_assets.py'),
                str(ROOT/'ModCarrerMode/data/club_browser')])
            run('room-roster-route', [sys.executable,'-B',str(SOURCE/'club_browser/test_room_players.py'),
                str(args.game_root),str(output/'room-roster-route')])
        elif group == 'native':
            if os.name != 'nt':
                run('native-requires-windows', [sys.executable, '-c', 'raise SystemExit(2)']); continue
            for script in sorted((SOURCE/'career_native/scripts/tests').glob('test_*.cmd')):
                run('native-'+script.stem, ['cmd', '/d', '/c', str(script)])
            run('native-competition', ['cmd', '/d', '/c', str(SOURCE/'common/test_competition_identity.cmd')])
            run('native-ui-theme', ['cmd', '/d', '/c', 'call', str(SOURCE/'common/test_custom_ui_theme.cmd'), str(output/'native-ui-theme')])
            run('native-jobs', ['cmd', '/d', '/c', str(SOURCE/'career_jobs_runtime/test.cmd')])
            run('native-camera', ['cmd', '/d', '/c', str(SOURCE/'scripts/test_first_person.cmd')])
            # Native room commands must remain direct across first entry and
            # re-entry; the Python heap-reader tests alone do not cover this.
            room_tests=SOURCE/'club_environment/room/native'
            compiler = Path(os.environ.get('VS_VCVARS64',
                r'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat'))
            for name in ('test_room_scene_command','test_room_direct_input','test_room_scene_state','test_room_background',
                         'test_room_free_camera','test_room_camera_projection','test_room_medical_startup'):
                stage=output/name;stage.mkdir(exist_ok=True);script=stage/'run.cmd'
                arguments=' '.join('"'+str(p)+'"' for p in room_collision_fixtures(stage)) if name=='test_room_free_camera' else ''
                script.write_text('@echo off\nsetlocal\ncall "'+str(compiler)+'" >nul\n'
                    'if errorlevel 1 exit /b 1\ncl /nologo /O2 /W3 /EHsc /std:c++17 /MT "'+str(room_tests/(name+'.cpp'))+'" '
                    '/Fe:test.exe /link user32.lib gdi32.lib ole32.lib d3d11.lib d3dcompiler.lib windowscodecs.lib\n'
                    'if errorlevel 1 exit /b 1\ntest.exe '+arguments+'\nif errorlevel 1 exit /b 1\nexit /b 0\n',encoding='utf8')
                run(name,['cmd','/d','/c',str(script)],cwd=stage)
            # Compile test executables in the report directory, not production folders.
            compiler = Path(os.environ.get('VS_VCVARS64',
                r'C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat'))
            covered = {'native_camera_channel_test', 'native_head_mesh_filter_test', 'native_first_person_test'}
            for test in sorted((SOURCE/'tests').glob('native_*test.cpp')):
                if test.stem in covered: continue
                stage = output/test.stem; stage.mkdir(exist_ok=True)
                script = stage/'run.cmd'
                dependencies=''
                if test.stem=='native_selector_bridge_test':
                    dependencies=' '.join('"'+str(SOURCE/'server16_py/d3d_overlay'/name)+'"' for name in
                        ('mod_xinput_gate.cpp','ranking_input_gate.cpp','crowd_bridge.cpp'))
                script.write_text('@echo off\nsetlocal\ncall "'+str(compiler)+'" >nul\n'
                    'if errorlevel 1 exit /b 1\n'
                    'cl /nologo /O2 /W3 /EHsc /std:c++17 /MT "'+str(test)+'" '+dependencies+' /Fe:test.exe '
                    '/link user32.lib gdi32.lib ole32.lib d3d11.lib d3dcompiler.lib dxgi.lib psapi.lib windowscodecs.lib bcrypt.lib\n'
                    'if errorlevel 1 exit /b 1\ntest.exe\nif errorlevel 1 exit /b 1\n'
                    + ('test.exe bootstrap\nif errorlevel 1 exit /b 1\n' if test.stem=='native_input_gate_test' else '')
                    + 'exit /b 0\n', encoding='utf8')
                run(test.stem, ['cmd', '/d', '/c', str(script)], cwd=stage)
    return 0 if rows and all(r['passed'] for r in rows) else 1

if __name__ == '__main__': raise SystemExit(main())
