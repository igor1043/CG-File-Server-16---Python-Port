"""Run the generated APT wrappers in the bounded ActionScript VM."""
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent/'apt_vendor')]
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
            if name=='GetStadiumYearBuilt':return owner.get('year')
            if name=='LocalizeInteger':
                assert isinstance(owner,Object) and owner.get('native_localization') is True
                return format(int(args[0]),',')
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
            vm.global_.set('ION_Localization',Object({'native_localization':True,'LocalizeInteger':Native('LocalizeInteger')}))
            text=Object({name:Object({'textWidth':70}) for name in fields});owner=Object({'mcTextGroup':text,'Server16OriginalUpdate':Native('original')})
            for capacity,year,cap_visible,year_visible in [(-1,0,False,False),(25000,1960,True,True),(0,1960,False,True),(0,10000000,False,False),(50000,10000000,True,False),(50000,10040001,True,True),(0,10000001,False,True)]:
                calls.clear();vm.invoke(fn,owner,[Object({'capacity':capacity,'year':year})])
                assert calls[0][0]=='original'
                assert all(text.get(name).get('_visible') is cap_visible for name in fields[:2])
                assert all(text.get(name).get('_visible') is year_visible for name in fields[2:4])
                assert text.get(fields[4]).get('_visible') is (cap_visible and year_visible)
                if year>10000000:
                    assert text.get('mYearName').get('text').encode('latin1').decode('utf8')=='PÚBLICO'
                    assert text.get('mYearValue').get('text')==format(year-10000001,',')
        print(file+': custom and native fallback behavior passed')

if __name__=='__main__':main(Path(sys.argv[1]))
