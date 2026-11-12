"""Extend GameSettings with native scoreboard and per-fixture attendance rows."""
from pathlib import Path
import hashlib,json,os,struct,sys
from .scoreboard_options import discover,selected_index

CLASS=('game','screens','settings','GameSettings')
FULL='.'.join(CLASS)
ROW=65000
CROWD_ROW=65001
CROWD_VALUES=(-1,*range(0,101,5))
MARKER=b'S16ScoreboardInstalled\0'


def write_native_big(big,path):
    """Retain every original native geometry/texture group when appending code."""
    from formats import chunk_wrap
    entries=[(name,bytes(entry.data)) for name,entry in big.entries.items()]
    header=16+sum(9+len(name.encode('latin1')) for name,_ in entries)
    offset=(header+63)//64*64;directory=bytearray();payload=bytearray(offset-header)
    for name,blob in entries:
        pad=-offset%64;payload.extend(bytes(pad));offset+=pad
        directory.extend(struct.pack('>II',offset,len(blob))+name.encode('latin1')+b'\0')
        payload.extend(blob);offset+=len(blob)
    content=b'BIGF'+struct.pack('<I',offset)+struct.pack('>II',len(entries),header)+directory+payload
    Path(path).write_bytes(chunk_wrap(content,big.wrapper) if big.wrapper else content)


def build(game,original,output,manifest):
    game=Path(game);source=game/'ModCarrerMode/source/club_environment'
    os.environ['SERVER16_GAME_ROOT']=str(game)
    for folder in (source/'vendor',source/'bank',source/'preview',source):
        if str(folder) not in sys.path:sys.path.insert(0,str(folder))
    from formats import BigFile,AptFile,Reader
    from apt_actions import Actions
    import build_screen as b
    from build_preview import Code as NativeCode
    big=BigFile(original);apt=AptFile(big);actions=Actions(apt).read_all()
    if actions.errors or MARKER in apt.data:raise ValueError('Use a tela original válida de opções de jogo')
    registration=next(c for c in apt.root_frames[0] if isinstance(c,tuple) and c[0]=='init' and c[1]==apt.exports['__Packages.'+FULL])
    original_code=actions.cache[registration[-1]]
    if original_code[-1].op!=0:raise ValueError('Registro nativo de opções desconhecido')
    catalog=discover(game);initial=selected_index(game,catalog)
    data=apt.data;data.extend(bytes(-len(data)%8));start=len(data)
    data.extend(data[registration[-1]:original_code[-1].offset])
    # Code.function's default class is used by other generators. Keep our
    # class private instead of changing a shared module global in Server16.
    class Code(NativeCode):
        def function(self,name,count,body,constructor=False):
            self.expr(b.path(*CLASS,'prototype'));self.string(name)
            self.op(142);self.align();at=len(self.data);self.data.extend(bytes(8));self.fixups.append((at,''))
            self.data.extend(struct.pack('<IHH',count,12,41))
            at=len(self.data);self.data.extend(bytes(8));self.parameters.append((at,count))
            size_at=len(self.data);self.data.extend(bytes(4));self.align()
            self.data.extend(struct.pack('<I',0x98765432));self.align();self.data.extend(struct.pack('<Q',0x12345678))
            body_at=len(self.data);body(self);self.op(118);self.op(62)
            struct.pack_into('<I',self.data,size_at,len(self.data)-body_at);self.op(79)
    a=Code(data);P=b.prop;R=b.reg;T=b.this;G=b.G;EQ=b.equal;CALL=b.call
    proto=b.path(*CLASS,'prototype');index=lambda obj,key:('index',obj,key)
    global_choice='Server16ScoreboardChoice';global_catalog='Server16ScoreboardCatalog'
    already=a.uid();a.expr(P(proto,'S16ScoreboardInstalled'));a.branch(already)
    a.set(proto,'S16ScoreboardInstalled',True)
    a.expr(proto);a.string('S16InitialScoreboard');a.op(183)
    initial_offset=len(data);data.extend(struct.pack('<i',initial));a.op(79)
    originals={'InitGameSetting':'S16BaseInit','GetCurrentSettingValue':'S16BaseCurrent',
        'GetDefaultSettingValue':'S16BaseDefault','SetCurrentSettingValue':'S16BaseSet',
        'OnChangeCallback':'S16BaseChange','LocalEventHandler':'S16BaseInput',
        'OnExitScreen':'S16BaseExit','ResetGameSettings':'S16BaseReset'}
    for method,backup in originals.items():a.set(proto,backup,P(proto,method))
    a.function('S16ScoreboardLabels',0,lambda a:a.ret(('array',catalog.labels)))
    a.function('S16ScoreboardValues',0,lambda a:a.ret(('array',tuple(range(len(catalog.values))))))
    a.function('S16ScoreboardDescription',0,lambda a:a.ret('Escolha o placar e volte para aplicar pelo Server16. Automático mantém as regras por competição. Requer o módulo ScoreBoard ativo.'))
    a.function('S16ScoreboardEnabled',0,lambda a:a.ret(True))
    a.function('S16CrowdLabels',0,lambda a:a.ret(('array',('Automático',*(str(v)+'%' for v in CROWD_VALUES[1:])))))
    a.function('S16CrowdValues',0,lambda a:a.ret(('array',tuple(range(len(CROWD_VALUES))))))
    a.function('S16CrowdDescription',0,lambda a:a.ret('Ocupação do estádio nesta partida. Automático usa a regra de público do mod; a escolha manual não altera outras partidas.'))
    def init(a):
        changed=('bin',17,EQ(EQ(G(global_catalog),catalog.signature),False),EQ(G(global_choice),None))
        a.when(changed,lambda a:(a.set(b.GLOBAL,global_catalog,catalog.signature),a.set(b.GLOBAL,global_choice,T('S16InitialScoreboard'))))
        a.when(EQ(T('S16ScoreboardDirty'),None),lambda a:a.set(R(1),'S16ScoreboardDirty',False))
        a.when(EQ(T('S16CrowdChoice'),None),lambda a:(a.set(R(1),'S16CrowdChoice',0),a.set(R(1),'S16CrowdDirty',False)))
        category=index(P(T('mcData'),'categories'),P(P(G('Settings'),'eCategory'),'MATCH'))
        def insert(a):
            descriptor=a.object(dict(id=ROW,title='Scoreboard',controlType='toggle',currentValue=G(global_choice),
                labels=P(proto,'S16ScoreboardLabels'),values=P(proto,'S16ScoreboardValues'),
                description=P(proto,'S16ScoreboardDescription'),isEnabled=P(proto,'S16ScoreboardEnabled'),
                isVisible=P(proto,'S16ScoreboardEnabled')))
            a.expr(P(T('mcData'),'settings'));a.expr(ROW);a.expr(descriptor);a.op(79)
            a.do(P(category,'settings'),'push',ROW);a.set(category,'S16ScoreboardInstalled',True)
        a.when(('bin',16,category,EQ(P(category,'S16ScoreboardInstalled'),None)),insert)
        def insert_crowd(a):
            descriptor=a.object(dict(id=CROWD_ROW,title='Ocupação do estádio',controlType='toggle',currentValue=T('S16CrowdChoice'),
                labels=P(proto,'S16CrowdLabels'),values=P(proto,'S16CrowdValues'),description=P(proto,'S16CrowdDescription'),
                isEnabled=P(proto,'S16ScoreboardEnabled'),isVisible=P(proto,'S16ScoreboardEnabled')))
            a.expr(P(T('mcData'),'settings'));a.expr(CROWD_ROW);a.expr(descriptor);a.op(79)
            a.do(P(category,'settings'),'push',CROWD_ROW);a.set(category,'S16CrowdInstalled',True)
        a.when(('bin',16,category,EQ(P(category,'S16CrowdInstalled'),None)),insert_crowd)
        a.do(R(1),'S16BaseInit')
    a.function('InitGameSetting',0,init)
    def current(a):
        a.when(EQ(R(3),ROW),lambda a:a.ret(G(global_choice)))
        a.when(EQ(R(3),CROWD_ROW),lambda a:a.ret(T('S16CrowdChoice')))
        a.ret(CALL(R(1),'S16BaseCurrent',R(2),R(3)))
    a.function('GetCurrentSettingValue',2,current)
    def default(a):
        a.when(EQ(R(3),CROWD_ROW),lambda a:a.ret(0))
        a.when(EQ(R(3),ROW),lambda a:a.ret(0));a.ret(CALL(R(1),'S16BaseDefault',R(2),R(3)))
    a.function('GetDefaultSettingValue',2,default)
    def setting(a):
        def crowd(a):
            valid=('bin',16,('bin',72,-1,R(4)),('bin',72,R(4),len(CROWD_VALUES)))
            a.when(valid,lambda a:(a.set(R(1),'S16CrowdChoice',R(4)),a.set(R(1),'S16CrowdDirty',True)))
            a.ret()
        a.when(EQ(R(3),CROWD_ROW),crowd)
        def own(a):
            valid=('bin',16,('bin',72,-1,R(4)),('bin',72,R(4),len(catalog.values)))
            a.when(valid,lambda a:(a.set(b.GLOBAL,global_choice,R(4)),a.set(R(1),'S16ScoreboardDirty',True)))
            a.ret()
        a.when(EQ(R(3),ROW),own);a.ret(CALL(R(1),'S16BaseSet',R(2),R(3),R(4)))
    a.function('SetCurrentSettingValue',3,setting)
    def changed(a):
        a.when(EQ(R(4),CROWD_ROW),lambda a:a.ret())
        a.when(EQ(R(4),ROW),lambda a:a.ret())
        a.ret(CALL(R(1),'S16BaseChange',R(2),R(3),R(4),R(5)))
    a.function('OnChangeCallback',4,changed)
    def commit(a):
        a.when(T('S16CrowdDirty'),lambda a:(
            a.do(b.ION,'SendSystemEvent','GameSettings','Server16MatchCrowd',
                b.plus(b.plus('S16CROWD1|',index(('array',CROWD_VALUES),T('S16CrowdChoice'))),'|END')),
            a.set(R(1),'S16CrowdDirty',False)))
        a.when(T('S16ScoreboardDirty'),lambda a:(
            a.do(b.ION,'SendSystemEvent','GameSettings','Server16MatchScoreboard',
                b.plus(b.plus('S16SCORE1|'+catalog.signature+'|',G(global_choice)),'|END')),
            a.set(R(1),'S16ScoreboardDirty',False)))
    a.function('S16CommitScoreboard',0,commit)
    def event(a):
        for key in ('BACK','ADVANCE'):
            a.when(EQ(R(2),P(G('INPUTCODE'),key)),lambda a:a.do(R(1),'S16CommitScoreboard'))
        a.ret(CALL(R(1),'S16BaseInput',R(2),R(3),R(4)))
    a.function('LocalEventHandler',3,event)
    a.function('OnExitScreen',0,lambda a:(a.do(R(1),'S16CommitScoreboard'),a.do(R(1),'S16BaseExit')))
    a.function('ResetGameSettings',0,lambda a:(a.set(b.GLOBAL,global_choice,0),a.set(R(1),'S16CrowdChoice',0),a.do(R(1),'S16BaseReset'),a.set(R(1),'S16ScoreboardDirty',True),a.set(R(1),'S16CrowdDirty',True)))
    a.label(already);a.op(0);a.finish()
    const=next(e for e in big.entries.values() if e.data[:4]==b'Apt1' or e.data[:17]==b'Apt constant file')
    root=Reader(const.data,20,apt.width).ptr();reader,_=apt.header(root);reader.i();frames=reader.ptr()
    count,table=struct.unpack_from('<I4xQ',data,frames);redirected=False
    for i in range(count):
        at=struct.unpack_from('<Q',data,table+8*i)[0]
        if struct.unpack_from('<i',data,at)[0]==8 and struct.unpack_from('<i',data,at+8)[0]==registration[1] and struct.unpack_from('<Q',data,at+16)[0]==registration[-1]:
            struct.pack_into('<Q',data,at+16,start);redirected=True
    if not redirected:raise ValueError('Registro original não encontrado')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    # An uncompressed BIG permits one verified initial-value update on startup
    # without importing the asset tools or rebuilding UI in the render loop.
    temporary=output.with_suffix('.big.scoreboard-building')
    big.wrapper=None;write_native_big(big,temporary)
    rebuilt=BigFile(temporary);check=AptFile(rebuilt);decoded=Actions(check).read_all()
    if decoded.errors or check.exports!=apt.exports:raise ValueError('Validação da tela falhou')
    if any(bytes(rebuilt.entries[name].data)!=bytes(entry.data) for name,entry in big.entries.items()):
        raise ValueError('A tela perdeu um recurso original')
    offset=rebuilt.entries[apt.entry.name].offset+initial_offset
    blob=temporary.read_bytes();stable=blob[:offset]+bytes(4)+blob[offset+4:]
    record=dict(schema=1,signature=catalog.signature,packages=catalog.packages,labels=catalog.labels,
        initial_value_offset=offset,ui_stable_sha256=hashlib.sha256(stable).hexdigest(),original_rows_preserved=True,crowd_row=CROWD_ROW)
    manifest=Path(manifest);manifest.parent.mkdir(parents=True,exist_ok=True)
    manifest_temp=manifest.with_suffix('.json.scoreboard-new');manifest_temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    os.replace(temporary,output);os.replace(manifest_temp,manifest)
    return record
