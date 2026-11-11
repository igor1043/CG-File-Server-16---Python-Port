"""Regressions for headers that a lenient APT VM accepts but FIFA crashes on."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_frontend_ui as builder
from validate_frontend_ui import validate_native_headers,main as validate_behavior
from formats import AptFile,BigFile,Placement,Reader
from apt_actions import Actions

class FrontendNativeHeaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='fifa_apt_header_')
        cls.folder=Path(cls.temp.name)
        for name,kind in [('backgroundfifa','background'),('stadiumpan','panorama')]:
            builder.build(ROOT/'native_mods/frontend_stadium/ui_templates'/f'{name}.big',cls.folder/f'{name}.big',kind)
        builder.build(ROOT/'native_mods/frontend_stadium/ui_templates/stadiumpan.big',
                      cls.folder/'stadiumpan_ultrawide.big','panorama',ultrawide=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def actions(self,name):return Actions(AptFile(BigFile(self.folder/f'{name}.big'))).read_all()

    def test_generated_ui_native_headers_and_behavior(self):validate_behavior(self.folder)

    def test_room_panorama_title_is_accented_on_both_text_layers(self):
        from apt_vm import VM,Function,Object,Native
        actions=self.actions('stadiumpan')
        def callback(name,owner,args):
            if name=='GetStadiumCapacity':return 0
            if name=='GetStadiumYearBuilt':return 0
        vm=VM(callback)
        for block in actions.cache.values():vm.run(block)
        fn=vm.path('game.screens.misc.StadiumPan.prototype').get('Update')
        fields=('mCapacityName','mCapacityValue','mYearName','mYearValue','mcDivderBottomVertical','mStadiumName','mStadiumNameShadow','mcHorizontalDivider')
        text=Object({name:Object({'textWidth':70}) for name in fields})
        text.get('mStadiumName').set('text','SERVER16_DRESSING_ROOM')
        vm.invoke(fn,Object({'mcTextGroup':text}),[Object({'capacity':0,'year':0})])
        for name in ('mStadiumName','mStadiumNameShadow'):
            self.assertEqual(text.get(name).get('text').encode('latin1').decode('utf8'),'Vestiário 3D')

    def test_ultrawide_hides_only_the_gradient_and_keeps_the_crest_layout(self):
        def placements(name):
            apt=self.actions(name).apt
            return {(c.id,p.depth):(p.name,p.matrix,p.flags,p.color,p.bias) for c in apt.characters.values()
                    for frame in c.frames for p in frame if isinstance(p,Placement)}
        normal=placements('stadiumpan')
        wide=placements('stadiumpan_ultrawide')
        self.assertEqual(normal.keys(),wide.keys())
        self.assertEqual([key for key in normal if normal[key]!=wide[key]],[(19,4)])
        self.assertEqual(wide[19,4][1],normal[19,4][1])
        self.assertEqual(wide[19,4][2],normal[19,4][2]|8)
        self.assertEqual(wide[19,4][3:],(0,0))
        self.assertEqual(normal[19,4][3],0xffffffff)

    def test_null_function_name_rejected(self):
        actions=self.actions('backgroundfifa')
        wrapper=next(i for block in actions.cache.values() for i in block
                     if i.op==142 and i.value['params']==[(3,'strImageId')])
        reader=Reader(actions.apt.data,wrapper.offset+1,8);reader.align()
        struct.pack_into('<Q',actions.apt.data,reader.pos,0)
        with self.assertRaisesRegex(ValueError,'name pointer'):validate_native_headers(actions)

    def test_register_underallocation_rejected(self):
        actions=self.actions('stadiumpan')
        wrapper=next(i for block in actions.cache.values() for i in block
                     if i.op==142 and i.value['params']==[(5,'stadAssign')])
        reader=Reader(actions.apt.data,wrapper.offset+1,8);reader.ptr()
        reader.pos=(reader.pos+3)//4*4;reader.i()
        struct.pack_into('<h',actions.apt.data,reader.pos,5)
        with self.assertRaisesRegex(ValueError,'register allocation'):validate_native_headers(actions)

    def test_original_native_entry_points_preserved(self):
        for name in ('backgroundfifa','stadiumpan'):
            generated=self.actions(name)
            original=Actions(AptFile(BigFile(ROOT/'native_mods/frontend_stadium/ui_templates'/f'{name}.big'))).read_all()
            self.assertEqual(len(generated.functions),len(original.functions))
            self.assertEqual(sorted((m['flags'],m['registers'],m['params']) for m,b in generated.functions),
                             sorted((m['flags'],m['registers'],m['params']) for m,b in original.functions))

if __name__=='__main__':unittest.main()
