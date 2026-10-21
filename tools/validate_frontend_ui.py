"""Run the generated APT wrappers in the bounded ActionScript VM."""
import sys
from pathlib import Path
sys.path[:0]=['U:/fifa 16/ScoreboardStudio']
from formats import AptFile,BigFile
from apt_actions import Actions
from apt_vm import VM,Function,Object,Native

def main(root):
    for file,kind in [('backgroundfifa.big','background'),('stadiumpan.big','panorama')]:
        ac=Actions(AptFile(BigFile(root/file))).read_all();calls=[]
        def callback(name,owner,args):
            calls.append((name,args))
            if name=='original':return 'original-result'
            if name=='GetStadiumCapacity':return owner.get('capacity')
        vm=VM(callback)
        for block in ac.cache.values():vm.run(block)
        path='game.background.BackgroundFIFA.prototype' if kind=='background' else 'game.screens.misc.StadiumPan.prototype'
        prototype=vm.path(path);method='LoadImage' if kind=='background' else 'Update'
        fn=prototype.get(method)
        assert isinstance(fn,Function) and isinstance(prototype.get('Server16Original'+method),Function)
        if kind=='background':
            image=Object();owner=Object({'mcImage':image,'Server16OriginalLoadImage':Native('original'),'LoadImageComplete':Native('complete')})
            assert vm.invoke(fn,owner,['server16_frontend_clear']) is True
            assert image.get('_visible') is False and owner.get('m_isLoaded') is True
            assert [n for n,a in calls]==['complete'];calls.clear()
            assert vm.invoke(fn,owner,['BOOTFLOW'])=='original-result'
            assert image.get('_visible') is True and calls==[('original',['BOOTFLOW'])]
        else:
            fields=('mCapacityName','mCapacityValue','mYearName','mYearValue','mcDivderBottomVertical')
            text=Object({name:Object() for name in fields});owner=Object({'mcTextGroup':text,'Server16OriginalUpdate':Native('original')})
            for capacity,visible in [(-1,False),(25000,True),(-1,False)]:
                vm.invoke(fn,owner,[Object({'capacity':capacity})])
                assert all(text.get(name).get('_visible') is visible for name in fields)
        print(file+': custom and native fallback behavior passed')

if __name__=='__main__':main(Path(sys.argv[1]))
