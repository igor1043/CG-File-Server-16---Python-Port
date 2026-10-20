"""Expand the two existing native deal slides, preserving the rest of the hub."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def expand(text):
    for slide,prefix,first in (('529','TOPDEAL',0),('530','LASTDEAL',3)):
        pattern=rf'<subtile[23]\b[^>]*\bID="{slide}"[^>]*>.*?</subtile[23]>'
        def replace(match):
            node=ET.fromstring(match[0])
            template=next(n for n in node if n.attrib.get('TYPE')=='component')
            attrs=dict(template.attrib)
            for child in list(node):
                if child.attrib.get('TYPE')=='component':node.remove(child)
            for i in range(10):
                item=dict(attrs,ID=f'{prefix}{first+i}',WIDTH='410',HEIGHT='100',
                          X=str(6+(i//5)*424),Y=str(76+(i%5)*104))
                item.pop('REL_TARGET',None);item.pop('REL_Y',None)
                ET.SubElement(node,'data',item)
            return ET.tostring(node,encoding='unicode')
        text,count=re.subn(pattern,replace,text,flags=re.S)
        if count!=1:raise ValueError(f'Expected exactly one native deal slide {slide}')
    return text


if __name__=='__main__':
    path=Path(__file__).resolve().parents[1]/'native_mods/career_overlay/layout/careermanagerhubcfg.xml'
    path.write_text(expand(path.read_text(encoding='utf8')),encoding='utf8')
