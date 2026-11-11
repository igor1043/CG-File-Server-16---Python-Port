"""Run the production scene scripts with Lua 5.1 (requires lupa.lua51)."""
import argparse
import ast
from itertools import permutations
from pathlib import Path
import re
import sys
import unittest

parser = argparse.ArgumentParser()
parser.add_argument('--lua-python-path', type=Path)
args, remaining = parser.parse_known_args()
if args.lua_python_path:
    sys.path.insert(0, str(args.lua_python_path))
from lupa.lua51 import LuaError, LuaRuntime

SOURCE = Path(__file__).resolve().parent.parent
SCRIPTS = {
    'var': (SOURCE / 'var_cabin/var_cabin.lua').read_text(),
    'smoke': (SOURCE / 'smoke_machine/smoke_machine.lua').read_text(),
}
native = (SOURCE / 'mascot_photographer/mascot_goal_line.cpp').read_text()
format_body = native.split('const int size=snprintf(script,sizeof(script),', 1)[1].split('ready,animated,', 1)[0]
mascot_template = ''.join(ast.literal_eval(s) for s in re.findall(r'"(?:\\.|[^"\\])*"', format_body))


def mascot_script(index=1, available=True):
    status = '[7]=true,' if available else ''
    return mascot_template % (status, status, index, index, index, index, index)


def environment():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
        assert(_VERSION == 'Lua 5.1')
        db={sle={}};rows={};creates=0;delayed=false;updates=0
        gSportsRNA={}
        function gSportsRNA:GetTable(name,index)
            if name=='wvWipe' then return {leagueID=7} end
            assert(rows[index], 'RNA not ready');return rows[index]
        end
        function gSportsRNA:GetInt(row,key) return row[key] end
        function SleUpdate(i)
            updates=updates+1
            local s=db.sle[i];s.isMascot=(s.sletype==1 and 1 or 0)
            s.isVarCabin=0;s.isSmokeMachine=0;s.isEntranceProps=0
        end
        function GetTexture(i) return 'base_texture' end
        function GetRMSle(i,m) return 'base_model' end
        function CreateSleVariations(gr,batch,sles) end
        gRenderables={}
        function gRenderables:Create(name,index)
            creates=creates+1;return {index=index}
        end
        function gRenderables:AddSubObject(batch,actor,kind)
            if not delayed then rows[actor.index]={sletype=kind,sleindex=1} end
            db.sle[actor.index]={sletype=kind,teamid=7}
        end
        function new_scene()
            rows={};gRenderObj={batchSle={},sles={}}
        end
    ''')
    return lua


class SceneScripts(unittest.TestCase):
    def test_factory_retries_follow_current_scene(self):
        for name, prefix in [('var', 'FIFA16_VAR_CABIN'), ('smoke', 'FIFA16_SMOKE_MACHINE')]:
            with self.subTest(module=name):
                lua = environment()
                lua.execute(SCRIPTS[name])
                create = lua.globals()[prefix + '_CREATE_LIVE']
                create()  # gRenderObj is not available yet.
                self.assertEqual(lua.globals().creates, 0)
                lua.execute('new_scene()')
                create(); create()
                self.assertEqual(lua.globals().creates, 1)
                lua.execute('new_scene()')  # Old LIVE_CREATED is still true.
                create(); create()
                self.assertEqual(lua.globals().creates, 2)
                lua.execute('rows={};gRenderObj.sles[0]=nil')  # Same table, new contents.
                create(); create()
                self.assertEqual(lua.globals().creates, 3)

    def test_delayed_rna_does_not_duplicate_pending_actor(self):
        for name, prefix in [('var', 'FIFA16_VAR_CABIN'), ('smoke', 'FIFA16_SMOKE_MACHINE')]:
            with self.subTest(module=name):
                lua = environment()
                lua.execute(SCRIPTS[name])
                lua.execute('new_scene();delayed=true')
                create = lua.globals()[prefix + '_CREATE_LIVE']
                for _ in range(8):
                    create()
                self.assertEqual(lua.globals().creates, 1)
                lua.execute('new_scene()')
                create()
                self.assertEqual(lua.globals().creates, 2)

    def test_existing_actor_and_rna_capacity(self):
        for name, prefix, kind in [('var', 'FIFA16_VAR_CABIN', 3), ('smoke', 'FIFA16_SMOKE_MACHINE', 16)]:
            with self.subTest(module=name):
                lua = environment()
                lua.execute(SCRIPTS[name])
                lua.execute(f'new_scene();gRenderObj.sles[41]={{}};rows[41]={{sletype={kind},sleindex=1}}')
                create = lua.globals()[prefix + '_CREATE_LIVE']
                create()
                self.assertEqual(lua.globals().creates, 0)
                lua.execute('new_scene();for i=0,175 do gRenderObj.sles[i]={} end')
                create()
                self.assertEqual(lua.globals().creates, 0)
                self.assertFalse(lua.globals()[prefix + '_LIVE_CREATED'])

    def test_mascot_refresh_preserves_later_callbacks(self):
        lua = environment()
        lua.execute('db.sle[1]={sletype=1,teamid=7}')
        lua.execute(mascot_script(available=False))
        self.assertEqual(lua.globals().db.sle[1].isMascot, 0)
        lua.execute('''
            laterUpdates=0;laterModels=0
            local update=SleUpdate;local model=GetRMSle
            function SleUpdate(i) laterUpdates=laterUpdates+1;update(i) end
            function GetRMSle(i,m) laterModels=laterModels+1;return model(i,m) end
        ''')
        for _ in range(4):
            lua.execute(mascot_script())
        self.assertEqual(lua.globals().db.sle[1].isMascot, 1)
        self.assertEqual(lua.globals().laterUpdates, 4)
        self.assertEqual(lua.globals().laterModels, 4)
        self.assertEqual(lua.globals().updates, 5)

    def test_all_module_orders_preserve_model_dispatch(self):
        for order in permutations(('var', 'smoke', 'mascot')):
            with self.subTest(order=order):
                lua = environment()
                lua.execute('''
                    db.sle[1]={sletype=1,teamid=7}
                    db.sle[2]={sletype=3,teamid=7};rows[2]={sletype=3,sleindex=1}
                    db.sle[3]={sletype=16,teamid=7};rows[3]={sletype=16,sleindex=1}
                    FIFA16_VAR_CABIN_HOOK_READY=true;FIFA16_SMOKE_MACHINE_HOOK_READY=true
                ''')
                for name in order:
                    lua.execute(mascot_script() if name == 'mascot' else SCRIPTS[name])
                lua.execute(mascot_script())
                lua.execute('SleUpdate(1);SleUpdate(2);SleUpdate(3)')
                model = lua.globals().GetRMSle
                self.assertIn('mascot/7/model_animated.rx3', model(1, 0))
                self.assertIn('var_cabin/model.rx3', model(2, 0))
                self.assertIn('smoke_machine/model.rx3', model(3, 0))

    def test_failed_mascot_refresh_clears_completion(self):
        lua = environment()
        lua.execute('db.sle[1]={sletype=1,teamid=7}')
        lua.execute(mascot_script())
        self.assertTrue(lua.globals().FIFA16_MASCOT_REFRESH_DONE)
        lua.execute("function GetTexture(i) error('temporary unavailability') end")
        with self.assertRaises(LuaError):
            lua.execute(mascot_script())
        self.assertFalse(lua.globals().FIFA16_MASCOT_REFRESH_DONE)

    def test_bootstrap_and_runtime_refresh_are_idempotent(self):
        for name, prefix in [('var', 'FIFA16_VAR_CABIN'), ('smoke', 'FIFA16_SMOKE_MACHINE')]:
            with self.subTest(module=name):
                lua = environment()
                lua.execute(SCRIPTS[name])
                lua.execute('new_scene();CreateSleVariations(gRenderables,gRenderObj.batchSle,gRenderObj.sles)')
                lua.execute('laterUpdates=0;local base=SleUpdate;function SleUpdate(i) laterUpdates=laterUpdates+1;base(i) end')
                lua.execute(SCRIPTS[name])
                create = lua.globals()[prefix + '_CREATE_LIVE']
                create(); create()
                lua.execute('SleUpdate(0)')
                self.assertEqual(lua.globals().creates, 1)
                self.assertEqual(lua.globals().laterUpdates, 1)
                self.assertEqual(lua.globals().updates, 1)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *remaining])
