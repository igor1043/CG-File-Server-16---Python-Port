"""Small native GameSettings extension; never replace stock setting controls."""
from pathlib import Path
import io,struct


def add_preview(game,big,apt,stadium):
    if not stadium or not stadium.get('preview'):return False
    from PIL import Image,ImageOps
    from formats import BigFile,AptFile,Reader,Entry
    template=Path(game)/'ModCarrerMode/source/tools/career_branding/originals/careerhubwidget.big'
    if not template.is_file():return False
    with Image.open(stadium['preview']) as image:
        image=ImageOps.fit(image.convert('RGB'),(480,270),method=Image.Resampling.LANCZOS)
        stream=io.BytesIO();image.save(stream,format='DDS',pixel_format='DXT1');dds=bytearray(stream.getvalue())
        struct.pack_into('<I',dds,20,len(dds)-128);struct.pack_into('<I',dds,88,0)
    panel=AptFile(BigFile(template));data=apt.data
    const=next(e for e in big.entries.values() if e.data[:4]==b'Apt1' or e.data[:17]==b'Apt constant file')
    root=Reader(const.data,20,apt.width).ptr();count,table=struct.unpack_from('<I4xQ',data,root+56)
    chars=[struct.unpack_from('<Q',data,table+i*8)[0] for i in range(count)]
    def append(raw):
        data.extend(bytes(-len(data)%8));at=len(data);data.extend(raw);return at
    def char(raw):
        ident=len(chars);chars.append(append(raw));return ident
    tex=len(chars);raw=bytearray(panel.data[panel.characters[1].offset:panel.characters[1].offset+40]);struct.pack_into('<I',raw,32,tex);char(raw)
    shape=len(chars);raw=bytearray(panel.data[panel.characters[2].offset:panel.characters[2].offset+56]);struct.pack_into('<I',raw,16,tex<<16);struct.pack_into('<4fI',raw,32,0,0,240,135,shape);char(raw)
    geo=bytearray(panel.big.entries['3'].data[:96]);geo.extend(b''.join(struct.pack('<8f',x,y,0,0,0,0,0,0) for x,y in ((0,135),(0,0),(240,0),(240,0),(240,135),(0,135))))
    for off,value in ((0,len(geo)),(16,len(geo)-16),(32,len(geo)-32),(52,tex)):struct.pack_into('<I',geo,off,value)
    struct.pack_into('<6f',geo,64,2,0,0,2,0,0)
    # Preserve the native grouped order: geometry, sg1, DDS, sg2, constants.
    additions={str(shape+1):bytes(geo),str(tex+1):bytes(dds)};ordered={}
    for key,entry in big.entries.items():
        if key=='sg1':
            name=str(shape+1);ordered[name]=Entry(name,0,len(geo),0,bytes(geo),bytearray(geo),False)
        if key=='sg2':
            name=str(tex+1);ordered[name]=Entry(name,0,len(dds),0,bytes(dds),dds,False)
        ordered[key]=entry
    big.entries=ordered
    # A fixed native placement is cheap and contains only this match's image.
    clip=apt.characters[apt.exports['game.screens.settings.GameSettings']]
    frame=clip.frames[0];placement=next(c for c in frame if getattr(c,'name',None)=='mcSettingImagePlaceHolder')
    raw=bytearray(data[placement.offset:placement.offset+80]);name=append(b'S16StadiumPhoto\0')
    struct.pack_into('<iii6f',raw,8,46,9100,shape,1,0,0,1,882,332);struct.pack_into('<Q',raw,56,name)
    inner=bytearray(raw);struct.pack_into('<iii6f',inner,8,14,1,shape,1,0,0,1,0,0);struct.pack_into('<Q',inner,56,0)
    innerptr=append(inner);innercontrols=append(struct.pack('<Q',innerptr));innerframe=append(struct.pack('<I4xQ',1,innercontrols))
    sprite=bytearray(data[clip.offset:clip.offset+56]);struct.pack_into('<I4xQ',sprite,32,1,innerframe);spriteid=char(sprite)
    struct.pack_into('<i',raw,16,spriteid);placed=append(raw)
    controls=[c.offset if hasattr(c,'offset') else None for c in frame]
    # Keep non-placement native controls too, via the original pointer table.
    _,frames=struct.unpack_from('<I4xQ',data,clip.offset+32)
    n,ptr=struct.unpack_from('<I4xQ',data,frames)
    controls=[struct.unpack_from('<Q',data,ptr+i*8)[0] for i in range(n)]+[placed]
    newptr=append(struct.pack('<'+'Q'*len(controls),*controls));struct.pack_into('<I4xQ',data,frames,len(controls),newptr)
    charptr=append(struct.pack('<'+'Q'*len(chars),*chars));struct.pack_into('<I4xQ',data,root+56,len(chars),charptr)
    return True


def extend(a,b,proto,stadium,has_photo):
    P=b.prop;R=b.reg;T=b.this;EQ=b.equal;CALL=b.call;G=b.G
    index=lambda obj,key:('index',obj,key)
    stadium_id=P(P(G('Settings'),'eSetting'),'STADIUM')
    a.function('S16IsStadiumSetting',0,lambda a:a.ret(('bin',16,('not',EQ(stadium_id,None)),EQ(T('m_nSettingEnum'),stadium_id))))
    def find(a):
        a.when(EQ(T('S16OptionsStarted'),True),lambda a:a.ret())
        a.set(R(1),'S16OptionsStarted',True)
        if stadium:
            descriptor=index(P(T('mcData'),'settings'),stadium_id)
            def override(a):
                a.when(P(descriptor,'S16OriginalLabels'),lambda a:None,lambda a:a.set(descriptor,'S16OriginalLabels',P(descriptor,'labels')))
                a.set(descriptor,'labels',P(proto,'S16StadiumLabels'))
            a.when(descriptor,override)
        a.set(R(1),'S16PreviousFrame',T('onEnterFrame'));a.set(R(1),'onEnterFrame',T('S16OptionsFrame'))
        a.set(R(1),'S16OptionsFrames',0)
        a.do(b.ION,'SendSystemEvent','GameSettings','Server16OptionsEnter','ENTER')
    a.function('S16FindStadiumSetting',0,find)
    if stadium:
        def labels(a):
            a.expr(CALL(R(1),'S16OriginalLabels'));a.op(135);a.align();a.data.extend(struct.pack('<i',2));a.op(23)
            a.expr(CALL(R(1),'values'));a.op(135);a.align();a.data.extend(struct.pack('<i',3));a.op(23)
            # Only replace the selected injected slot; all other native labels remain.
            a.set(R(1),'S16LabelIndex',0);loop=a.uid();done=a.uid();a.label(loop)
            a.expr(('not',('bin',72,T('S16LabelIndex'),P(R(3),'length'))));a.branch(done)
            a.when(EQ(index(R(3),T('S16LabelIndex')),int(stadium['id'])),lambda a:(a.expr(R(2)),a.expr(T('S16LabelIndex')),a.expr(stadium['title']),a.op(79)))
            a.set(R(1),'S16LabelIndex',b.plus(T('S16LabelIndex'),1));a.branch(loop,False);a.label(done);a.ret(R(2))
        a.function('S16StadiumLabels',0,labels)
    def frame(a):
        a.when(T('S16PreviousFrame'),lambda a:a.do(R(1),'S16PreviousFrame'))
        a.set(R(1),'S16OptionsFrames',b.plus(T('S16OptionsFrames'),1))
        a.when(('bin',72,29,T('S16OptionsFrames')),lambda a:(a.set(R(1),'S16OptionsFrames',0),a.do(b.ION,'SendSystemEvent','GameSettings','Server16OptionsTick','tick')))
    a.function('S16OptionsFrame',0,frame)
    def help_(a):
        a.expr(CALL(R(1),'S16BaseHelp'));a.op(135);a.align();a.data.extend(struct.pack('<i',2));a.op(23)
        a.when(('not',R(2)),lambda a:(a.expr(('array',())),a.op(135),a.align(),a.data.extend(struct.pack('<i',2)),a.op(23)))
        a.when(CALL(R(1),'S16IsStadiumSetting'),lambda a:a.do(R(2),'push',CALL(b.path('ion','manager','HelpItem'),'CreateHelpTickerItem','OPTION_LEFT','Selecionar estádio')))
        a.ret(R(2))
    a.function('GetHelpContext',0,help_)
    def visual(a):
        if has_photo:
            a.set(T('S16StadiumPhoto'),'_visible',CALL(R(1),'S16IsStadiumSetting'))
            a.when(CALL(R(1),'S16IsStadiumSetting'),lambda a:a.set(T('mcSettingImagePlaceHolder'),'_visible',False),lambda a:a.set(T('mcSettingImagePlaceHolder'),'_visible',True))
        a.do(b.MANAGER('HelpManager'),'Update')
    a.function('S16StadiumVisual',0,visual)
    a.function('HighlightCallback',2,lambda a:(a.do(R(1),'S16BaseHighlight',R(2),R(3)),a.do(R(1),'S16StadiumVisual')))
    a.function('UnhighlightCallback',2,lambda a:(a.do(R(1),'S16BaseUnhighlight',R(2),R(3)),a.set(T('S16StadiumPhoto'),'_visible',False) if has_photo else None))
