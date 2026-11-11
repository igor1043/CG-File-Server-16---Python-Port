"""Integration contract between the native publisher and the installed hub."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'career_native'


class TransferCardsLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root=ET.parse(ROOT/'native_mods/career_overlay/layout/careermanagerhubcfg.xml').getroot()
        self.slides=[next(n for n in self.root.iter() if n.attrib.get('ID')==slide) for slide in ('529','530')]

    def test_component_ids_match_native_ranges_and_provider(self):
        header=(NATIVE/'src/host/career_transfer_cards.h').read_text()
        count=int(re.search(r'#define CAREER_TRANSFER_CARD_ROWS (\d+)',header)[1])
        latest=int(re.search(r'#define CAREER_TRANSFER_LATEST_FIRST (\d+)',header)[1])
        capacity=int(re.search(r'#define CAREER_TRANSFER_PROVIDER_ROWS (\d+)',header)[1])
        self.assertGreaterEqual(latest,count)
        self.assertGreaterEqual(capacity,latest+count)
        for node,prefix,first in zip(self.slides,('TOPDEAL','LASTDEAL'),(0,latest)):
            self.assertEqual(node.attrib['DATAPROVIDERID'],'CM_DEALS_DP')
            self.assertEqual(node.attrib['DESTINATION'],'')
            components=[n for n in node if n.attrib.get('TYPE')=='component']
            self.assertEqual([n.attrib['ID'] for n in components],[f'{prefix}{i}' for i in range(first,first+count)])

    def test_two_columns_with_no_clipping_or_overlap(self):
        for slide in self.slides:
            rects=[]
            for node in slide:
                if node.attrib.get('TYPE')!='component':continue
                a=node.attrib;x,y,w,h=[int(a[k]) for k in ('X','Y','WIDTH','HEIGHT')]
                self.assertGreaterEqual(x,0);self.assertLessEqual(x+w,846)
                self.assertGreaterEqual(y,100);self.assertLessEqual(y+h,604)
                self.assertFalse(any(x<X+W and X<x+w and y<Y+H and Y<y+h for X,Y,W,H in rects))
                rects.append((x,y,w,h))
            self.assertEqual(len({x for x,y,w,h in rects}),2)
            self.assertEqual(len({y for x,y,w,h in rects}),5)

    def test_first_transfers_fill_both_columns_before_starting_the_next_row(self):
        for slide in self.slides:
            rows=[n.attrib for n in slide if n.attrib.get('TYPE')=='component']
            self.assertEqual([(int(r['X']),int(r['Y'])) for r in rows[:4]],
                             [(18,100),(432,100),(18,200),(432,200)])
            subtitle=slide.find("data[@ID='TRANSFER_CARD_SUBTITLE']")
            self.assertIsNotNone(subtitle)
            self.assertLessEqual(int(subtitle.get('Y'))+int(subtitle.get('HEIGHT')),100)

    def test_empty_slots_stay_hidden_and_use_original_component(self):
        for slide in self.slides:
            for node in slide:
                if node.attrib.get('TYPE')!='component':continue
                self.assertEqual(node.attrib['VISIBLE'],'FALSE')
                self.assertEqual(node.attrib['PATH'],'game/components/FluxComponents/career/TransferInfo.swf')
                self.assertNotIn('REL_TARGET',node.attrib)

    def test_component_restyle_preserves_registration_actions_imports_and_textures(self):
        sys.path.insert(0,str(ROOT/'tools'))
        sys.path.insert(0,str(ROOT/'tools/apt_vendor'))
        from expand_career_transfer_cards import style_component
        from formats import BigFile,AptFile,Placement
        from apt_actions import Actions
        original=ROOT/'tools/career_branding/originals/transferinfo.big'
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'transferinfo.big';output.write_bytes(style_component(original))
            before,after=BigFile(original),BigFile(output)
            a,b=AptFile(before),AptFile(after)
            self.assertEqual(a.exports,b.exports)
            self.assertEqual(a.imports,b.imports)
            self.assertEqual((b.stage_width,b.stage_height),(396,92))
            actions=Actions(a).read_all();self.assertEqual(actions.errors,[])
            for start,instructions in actions.cache.items():
                end=instructions[-1].end
                self.assertEqual(a.data[start:end],b.data[start:end])
            self.assertEqual(style_component(output),output.read_bytes())
            for name in before.entries:
                if name!='0':self.assertEqual(before.entries[name].data,after.entries[name].data)
            self.assertEqual([c for c in a.root_frames[0] if isinstance(c,tuple)],
                             [c for c in b.root_frames[0] if isinstance(c,tuple)])
            before_names={p.name for p in a.characters[11].frames[0] if isinstance(p,Placement) and p.name}
            after_names={p.name for p in b.characters[11].frames[0] if isinstance(p,Placement) and p.name}
            self.assertEqual(before_names,after_names)
            for cid in (8,10):
                self.assertEqual(b.characters[cid].alignment,0)
                self.assertEqual(b.characters[cid].color,0xFFF1F5F8)

    def test_text_has_high_contrast_against_both_transfer_row_backgrounds(self):
        sys.path.insert(0,str(ROOT/'tools'))
        sys.path.insert(0,str(ROOT/'tools/apt_vendor'))
        from expand_career_transfer_cards import style_component
        from formats import BigFile,AptFile,Placement
        original=ROOT/'tools/career_branding/originals/transferinfo.big'
        def luminance(rgb):
            channels=[((rgb>>shift)&255)/255 for shift in (16,8,0)]
            linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
            return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'transferinfo.big';output.write_bytes(style_component(original))
            apt=AptFile(BigFile(output))
            panel=next(p for p in apt.characters[11].frames[0] if isinstance(p,Placement) and p.character==3)
            for cid in (8,10):
                a,b=sorted((luminance(apt.characters[cid].color),luminance(panel.bias)))
                self.assertGreater((b+.05)/(a+.05),7)
