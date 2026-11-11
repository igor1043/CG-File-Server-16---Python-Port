"""Lay out the two native deal slides without changing their data providers."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def expand(text):
    for slide,prefix,first,description in (
            ('529','TOPDEAL',0,'Maiores valores de transferência da carreira'),
            ('530','LASTDEAL',10,'Negócios mais recentes da carreira')):
        pattern=rf'<subtile[23]\b[^>]*\bID="{slide}"[^>]*>.*?</subtile[23]>'
        def replace(match):
            node=ET.fromstring(match[0])
            template=next(n for n in node if n.attrib.get('TYPE')=='component')
            attrs=dict(template.attrib)
            for child in list(node):
                if child.attrib.get('TYPE')=='component' or child.attrib.get('ID')=='TRANSFER_CARD_SUBTITLE':node.remove(child)
            title=next(n for n in node if n.attrib.get('ID')=='TITLE')
            title.attrib.update(WIDTH='798',HEIGHT='46',X='24',Y='12')
            ET.SubElement(node,'data',ID='TRANSFER_CARD_SUBTITLE',TYPE='text',
                          FORMAT='SS||left',TRANSLATE='FALSE',PARAM=description,
                          WIDTH='798',HEIGHT='24',X='24',Y='62')
            for i in range(10):
                item=dict(attrs,ID=f'{prefix}{first+i}',WIDTH='396',HEIGHT='92',
                          X=str(18+(i%2)*414),Y=str(100+(i//2)*100))
                item.pop('REL_TARGET',None);item.pop('REL_Y',None)
                ET.SubElement(node,'data',item)
            return ET.tostring(node,encoding='unicode')
        text,count=re.subn(pattern,replace,text,flags=re.S)
        if count!=1:raise ValueError(f'Expected exactly one native deal slide {slide}')
    return text


def style_component(source):
    """Refine the stock APT's visual fields; retain all native data bindings."""
    import struct
    import sys
    vendor=str(Path(__file__).resolve().parent/'apt_vendor')
    if vendor not in sys.path:sys.path.insert(0,vendor)
    from formats import AptFile,BigFile,Placement,Reader
    big=BigFile(source);apt=AptFile(big)
    export='game.components.FluxComponents.career.TransferInfo'
    assert apt.exports.get(export)==11
    assert apt.imports[6]==('game/globalComponents/globalComponents','game.globalComponents.ImageLoader')
    placements=[p for p in apt.characters[11].frames[0] if isinstance(p,Placement)]
    named={p.name:p for p in placements if p.name}
    matrices={
        'mcBackground':(3.96,0.,0.,92./120.,0.,0.),
        'mcPlayerIcon':(.76,0.,0.,.76,8.,8.),
        'mcSellingTeamIcon':(.75,0.,0.,.75,258.,44.),
        'mcSellingTeamIconDark':(.75,0.,0.,.75,258.,44.),
        'mcBuyingTeamIcon':(.75,0.,0.,.75,348.,44.),
        'mcBuyingTeamIconDark':(.75,0.,0.,.75,348.,44.),
        'txtPlayerName':(1.,0.,0.,1.,90.,8.),
        'txtAmount':(1.,0.,0.,1.,90.,44.),
    }
    for name,matrix in matrices.items():
        struct.pack_into('<6f',apt.data,named[name].matrix_offset,*matrix)
    # Reuse the original solid rectangle as a dark FIFA row background with light text. Its
    # symbol/depth stays in place, so ImageLoader and provider code are intact.
    panel=next(p for p in placements if p.character==3)
    struct.pack_into('<6f',apt.data,panel.matrix_offset,99.,0.,0.,23.,0.,0.)
    struct.pack_into('<II',apt.data,panel.matrix_offset+24,0xFF000000,0x00273543)
    arrow=next(p for p in placements if p.character==5)
    struct.pack_into('<6f',apt.data,arrow.matrix_offset,.6,0.,0.,.6,124.,30.)
    for cid,size,width in ((8,22.,290.),(10,21.,156.)):
        character=apt.characters[cid];reader,kind=apt.header(character.offset)
        assert kind==2
        struct.pack_into('<4f',apt.data,reader.pos,-2.,-2.,width,30.)
        reader.pos+=16;reader.i()
        struct.pack_into('<i',apt.data,reader.pos,0)
        struct.pack_into('<I',apt.data,character.color_offset,0xFFF1F5F8)
        struct.pack_into('<f',apt.data,character.font_offset,size)
    # Exported movie dimensions agree with the XML row box.
    constants=next(e for e in big.entries.values() if e.data[:4]==b'Apt1' or e.data[:17]==b'Apt constant file')
    reader=Reader(constants.data,20,apt.width);root=reader.ptr();reader,kind=apt.header(root)
    assert kind==9
    reader.i();reader.ptr();reader.ptr();reader.i();reader.ptr()
    struct.pack_into('<II',apt.data,reader.pos,396,92)
    return big.build()


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    path=root/'native_mods/career_overlay/layout/careermanagerhubcfg.xml'
    path.write_text(expand(path.read_text(encoding='utf8')),encoding='utf8')
    component=root/'artifacts/career_transfer_cards/transferinfo.big'
    component.parent.mkdir(parents=True,exist_ok=True)
    component.write_bytes(style_component(root/'tools/career_branding/originals/transferinfo.big'))
