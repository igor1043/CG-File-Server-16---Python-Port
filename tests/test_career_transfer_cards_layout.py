"""Integration contract between the native publisher and the installed hub."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
NATIVE=Path('U:/mods/FIFA Friends V12/ModCarrerMode/source/career_native')


class TransferCardsLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root=ET.parse(ROOT/'native_mods/career_overlay/layout/careermanagerhubcfg.xml').getroot()
        self.slides=[next(n for n in self.root.iter() if n.attrib.get('ID')==slide) for slide in ('529','530')]

    def test_component_ids_match_native_ranges_and_provider(self):
        header=(NATIVE/'src/host/career_transfer_cards.h').read_text()
        count=int(re.search(r'#define CAREER_TRANSFER_CARD_ROWS (\d+)',header)[1])
        for node,prefix,first in zip(self.slides,('TOPDEAL','LASTDEAL'),(0,3)):
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
                self.assertGreaterEqual(y,52);self.assertLessEqual(y+h,604)
                self.assertFalse(any(x<X+W and X<x+w and y<Y+H and Y<y+h for X,Y,W,H in rects))
                rects.append((x,y,w,h))
            self.assertEqual(len({x for x,y,w,h in rects}),2)
            self.assertEqual(len({y for x,y,w,h in rects}),5)

    def test_empty_slots_stay_hidden_and_use_original_component(self):
        for slide in self.slides:
            for node in slide:
                if node.attrib.get('TYPE')!='component':continue
                self.assertEqual(node.attrib['VISIBLE'],'FALSE')
                self.assertEqual(node.attrib['PATH'],'game/components/FluxComponents/career/TransferInfo.swf')
                self.assertNotIn('REL_TARGET',node.attrib)
