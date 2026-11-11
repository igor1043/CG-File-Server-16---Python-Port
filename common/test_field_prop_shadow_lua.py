"""Execute the emitted production bind scripts using Lua 5.1."""
import argparse,sys
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('script',type=Path);parser.add_argument('--dependencies',type=Path)
args=parser.parse_args()
if args.dependencies:sys.path.insert(0,str(args.dependencies))
from lupa.lua51 import LuaRuntime

def environment(key):
 lua=LuaRuntime(unpack_returned_tuples=True)
 lua.globals().fieldKey=key
 lua.execute('''
 assert(_VERSION=='Lua 5.1')
 object={};assets={};addAssets=0;links=0;reloads=0
 gRenderObj={flatShadow={},selfshadow={}}
 gRenderables={}
 function gRenderables:Find(t,i) assert(string.find(t,'server16_field_shadow_'..fieldKey..'_1',1,true) and i==0);return object end
 function gRenderables:AddAsset(o,lod,name,file) assert(o==object and lod==0);assert(not assets[name]);assets[name]=file;addAssets=addAssets+1 end
 function gRenderables:CreateMaterialFromAttribulator(o,lod,part,name,mat) assert(part=='prop_plastic' and mat=='prop_plastic') end
 function gRenderables:SetSubMesh(o,lod,part,mesh) meshExpression=mesh end
 function gRenderables:SetTexture(o,lod,part,group,name,source,texture) end
 function gRenderables:AddSubObject(parent,child,pass) assert(child==object);assert((parent==gRenderObj.flatShadow and pass==2) or (parent==gRenderObj.selfshadow and pass==4));links=links+1 end
 function gRenderables:Reload(o,mode) assert(mode==1);reloads=reloads+1;assert(assets.prop_plastic=='${S16FieldShadowObjects.'..fieldKey..'.model}');resolvedModel=S16FieldShadowObjects[fieldKey].model end
 gSportsRNA={GetTable=function()return{}end,GetInt=function()return 0 end}
 ''')
 return lua

script=args.script.read_text();lua=environment('stands');lua.execute(script);assert lua.globals().S16FieldShadowBound
lua.execute(script.replace('generic1/model.rx3','cbf/model.rx3').replace('standball_generic1_','standball_cbf_'));assert lua.globals().S16FieldShadowBound
assert lua.globals().links==0 and lua.globals().reloads==2 and lua.globals().addAssets==4
lua.execute('gRenderObj={flatShadow={},selfshadow={}}');lua.execute(script)
assert lua.globals().links==0 and lua.globals().addAssets==4
assert 'AddSubObject' not in script and 'ContextAddRenderable' not in script and 'missingShader' not in script
assert 'SetSubMesh' not in script, 'RX3 object labels must not filter out the only mesh'
balls=Path(str(args.script)+'.balls').read_text();lua=environment('balls')
lua.execute("db={ball={[1]={model=299}}};function GetRMBall(i,kind) assert(i==1 and kind==0);return 'data/sceneassets/ball/specificball_1043_7_0.rx3;' end")
lua.execute(balls);assert lua.globals().S16FieldShadowBound
assert lua.globals().resolvedModel=='data/sceneassets/ball/specificball_1043_7_0.rx3;data/sceneassets/ball/ball_299.rx3;data/sceneassets/ball/ball_23.rx3'
print('PASS Lua 5.1 resources, model changes and competition football fallback; no unchecked native AddSubObject calls in resource script')
