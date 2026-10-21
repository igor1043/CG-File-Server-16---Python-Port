"""Execute the actual installed Lua 5.1 callbacks against a mock RNA service."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,r'C:\Users\igorv\AppData\Local\Temp\server16_frontend_test_deps')
from lupa.lua51 import LuaRuntime
from tools.install_frontend_stadium import patched_stadium,patched_crowd


def main():
    lua=LuaRuntime(unpack_returned_tuples=True)
    original=Path(sys.argv[1]) if len(sys.argv)>1 else Path('U:/fifa 16/data/fifarna/lua/assets/stadium.lua')
    source=original.read_text(encoding='utf-8-sig')
    if '-- Server16 frontend stadium v1' not in source:source=patched_stadium(source)
    helper=(ROOT/'native_mods/frontend_stadium/frontend_stadium.lua').read_text()
    route='Server16FrontendRoutes[176] = {team=130022,model="custom/model.rx3",day="custom/day.rx3",night="custom/night.rx3",chairs="custom/NoSeats.rx3"}'
    def load(path):
        return helper if path.endswith('server16_frontend_stadium.lua') else route
    lua.globals().read_script=load
    lua.execute('gSportsRNA={}; function gSportsRNA:LoadScriptAsync(path) return read_script(path) end; function gSportsRNA:LoadScriptAsyncComplete(source) assert(loadstring(source))() end')
    lua.execute(source)  # Compiles the complete patched stadium.lua under Lua 5.1.
    lua.execute('db={stadium={[0]={stadiumID=176,lightType=1},[1]={stadiumID=176,lightType=1}}}')
    lua.execute('Server16FrontendUpdate(0); Server16FrontendUpdate(1)')
    assert lua.eval('GetRMStadModel(0)')=='custom/model.rx3;'
    assert lua.eval('GetRMStadTex(0)')=='custom/day.rx3;'
    lua.execute('db.stadium[0].lightType=3')
    assert lua.eval('GetRMStadTex(0)')=='custom/night.rx3;'
    assert lua.eval('db.stadium[0].homeTeamID')==130022
    assert lua.eval('db.stadium[0].homeTeamAssetId')==130022
    assert lua.eval('db.stadium[1].server16Frontend') is None
    crowd=Path('U:/fifa 16/data/fifarna/lua/assets/crowd.lua').read_text(encoding='utf-8-sig')
    if '-- Server16 frontend stadium v1' not in crowd:crowd=patched_crowd(crowd)
    lua.execute(crowd)
    lua.execute('db.crowd={[0]={stadiumID=22},[1]={stadiumID=22}}; function gSportsRNA:GetTable(name,idx) return idx end; function gSportsRNA:GetInt(table,key) return 176 end')
    # The crowd callback can run first. It must load the current route rather
    # than reuse the Lua table left by a previous visit to the same slot.
    lua.execute('Server16FrontendRoutes[176]={team=1,model="stale.rx3",chairs="old.rx3"}; Server16FrontendCrowdUpdate(0); Server16FrontendCrowdUpdate(1)')
    assert lua.eval('Server16FrontendChair(0)')=='custom/NoSeats.rx3;'
    assert lua.eval('db.crowd[0].homeKitTeamID')==130022
    assert lua.eval('db.crowd[0].stadiumID')==176
    assert lua.eval('db.crowd[1].stadiumID')==22
    assert lua.eval('Server16FrontendChair(1)')==''
    lua.execute('db.stadium[0].stadiumID=175; Server16FrontendUpdate(0)')
    assert lua.eval('Server16FrontendModel(0)')==''
    lua.execute('db.stadium[0].stadiumID=176; function gSportsRNA:LoadScriptAsyncComplete(source) error("unavailable") end; Server16FrontendUpdate(0)')
    assert lua.eval('Server16FrontendModel(0)')==''
    lua.execute('Server16FrontendCrowdUpdate(0)')
    assert lua.eval('Server16FrontendChair(0)')==''
    print('Lua 5.1: full stadium.lua/crowd.lua parse; day/night, crest identity, fresh crowd-before-stadium route, custom chairs, match isolation and load-failure fallback passed')

if __name__=='__main__':main()
