"""Append a native financial-start toggle to FIFA's original career Setup.

No base setting, row, art or navigation event is replaced. The extra option
queues an explicit creation-only request; the native career owner applies it.
"""
from pathlib import Path
import os,struct,json,hashlib,sys

CLASS=('game','screens','career','Setup')
FULL='.'.join(CLASS)
UI_PATH='data/ui/game/screens/career/setup.big'
AMOUNTS=(0,10_000,20_000,40_000,80_000,1_000_000,5_000_000,10_000_000,50_000_000,100_000_000,200_000_000,500_000_000)
LABELS=('Desativado','+10 mil','+20 mil','+40 mil','+80 mil','+1 milhão','+5 milhões','+10 milhões','+50 milhões','+100 milhões','+200 milhões','+500 milhões')
MARKER=b'S16FinancialInstalled\0'

def build(game,original,output):
    game=Path(game);source=game/'ModCarrerMode/source/club_environment'
    os.environ['SERVER16_GAME_ROOT']=str(game)
    for folder in (source/'vendor',source/'bank',source/'preview',source):
        if str(folder) not in sys.path:sys.path.insert(0,str(folder))
    from formats import BigFile,AptFile,Reader
    from apt_actions import Actions
    from build_preview import Code as NativeCode
    import build_screen as b
    from .scoreboard_options_ui import write_native_big
    big=BigFile(original);apt=AptFile(big);actions=Actions(apt).read_all()
    if actions.errors:raise ValueError(actions.errors)
    registration=next(c for c in apt.root_frames[0] if isinstance(c,tuple) and c[0]=='init' and c[1]==apt.exports['__Packages.'+FULL])
    original_code=actions.cache[registration[-1]]
    # Retain the unmodified native initializer preserved by our earlier build.
    # Rebuilding from the patched movie must not wrap our own methods again.
    if any(row.value=='S16FinancialInstalled' for row in original_code if isinstance(row.value,str)):
        prefix=bytes(apt.data[registration[-1]:registration[-1]+32]);candidates=[]
        for offset in range(0,registration[-1],8):
            if apt.data[offset:offset+32]!=prefix:continue
            code=actions.decode(offset)
            if code[-1].op==0 and not any(row.value=='S16FinancialInstalled' for row in code if isinstance(row.value,str)):
                candidates.append(code)
        if len(candidates)!=1:raise ValueError('Cannot identify the preserved native Setup initializer')
        original_code=candidates[0]
    if original_code[-1].op!=0:raise ValueError('Unexpected native Setup registration')
    data=apt.data;data.extend(bytes(-len(data)%8));start=len(data)
    data.extend(data[original_code[0].offset:original_code[-1].offset])
    class Code(NativeCode):
        def function(self,name,count,body,constructor=False):
            self.expr(b.path(*CLASS,'prototype'));self.string(name)
            self.op(142);self.align();at=len(self.data);self.data.extend(bytes(8));self.fixups.append((at,''))
            self.data.extend(struct.pack('<IHH',count,12,41))
            at=len(self.data);self.data.extend(bytes(8));self.parameters.append((at,count))
            size_at=len(self.data);self.data.extend(bytes(4));self.align()
            self.data.extend(struct.pack('<I',0x98765432));self.align();self.data.extend(struct.pack('<Q',0x12345678));begin=len(self.data)
            body(self);self.op(118);self.op(62);struct.pack_into('<I',self.data,size_at,len(self.data)-begin);self.op(79)
    a=Code(data);R=b.reg;P=b.prop;T=b.this;G=b.G;CALL=b.call;EQ=b.equal
    proto=b.path(*CLASS,'prototype');klass=b.path(*CLASS);ION=b.ION
    def index(obj,key):return ('bin',78,obj,key)
    installed=a.uid();a.expr(P(proto,'S16FinancialInstalled'));a.branch(installed)
    a.set(proto,'S16FinancialInstalled',True)
    for method in ('_InitComponentsData','_InitRowControlData','_LocalEventHandler','_OnExitScreen','_OnAnimateInComplete'):
        a.set(proto,'S16Base'+method,P(proto,method))
    def send(a,action,amount=0):
        a.do(ION,'SendSystemEvent','CareerSetup','Server16FinancialIncorporation',
             b.plus(b.plus('S16FUND1|'+action+'|',amount),'|END'))
    def init(a):
        a.do(R(1),'S16Base_InitComponentsData')
        a.set(R(1),'S16FinancialIndex',0);a.set(R(1),'S16FinancialAccepted',False)
        a.set(R(1),'S16FinancialRow',P(T('m_RowData'),'length'))
        descriptor=a.object(dict(NAME='S16Financial',TYPE=P(klass,'TYPE_TOGGLE'),LABEL='Incorporação Financeira',
            TITLE='Incorporação Financeira',DESC='Acrescenta o valor ao orçamento de transferências da nova carreira de treinador. Aplicado uma única vez ao iniciar, na moeda selecionada. Não altera carreiras existentes.',
            ASSET_ID='-1',SELECTED_INDEX=0))
        a.do(T('m_RowData'),'push',descriptor)
    a.function('_InitComponentsData',0,init)
    def rows(a):
        # The native provider only receives original row IDs. Restore the extra
        # row after it has populated its own toggles and link restrictions.
        a.expr(CALL(T('m_RowData'),'pop'));a.store(4)
        a.do(R(1),'S16Base_InitRowControlData');a.do(T('m_RowData'),'push',R(4))
        values=('array',tuple(a.object(dict(TEXT=label,VALUE=i,IS_LOCKED='0')) for i,label in enumerate(LABELS)))
        a.expr(T('m_TogglesData'));a.expr(T('S16FinancialRow'));a.expr(values);a.op(79)
        a.set(R(1),'S16FinancialControl',CALL(T('mcRowControl'),'getRowAtIndex',T('S16FinancialRow')))
        a.do(R(1),'_UpdateRow',T('S16FinancialControl'),T('S16FinancialRow'))
        for clip in ('txtButton','txtLink','mcCheckMark'):a.set(P(T('S16FinancialControl'),clip),'_visible',False)
        for clip in ('txtLabel','mcToggle'):a.set(P(T('S16FinancialControl'),clip),'_visible',True)
        a.do(R(1),'_PopulateToggle',T('S16FinancialControl'),T('S16FinancialRow'),T('S16FinancialIndex'))
    a.function('_InitRowControlData',0,rows)
    # Native page ownership is published after construction/animation, not
    # necessarily while the original row provider is being initialized.
    a.function('_OnAnimateInComplete',0,lambda a:(a.do(R(1),'S16Base_OnAnimateInComplete'),send(a,'BEGIN')))
    def event(a):
        a.set(R(1),'S16SelectedRow',CALL(T('mcRowControl'),'getSelectedIndex'))
        own=EQ(T('S16SelectedRow'),T('S16FinancialRow'))
        def change(delta):
            def change_body(a):
                a.set(R(1),'S16FinancialIndex',('bin',63,b.plus(b.plus(T('S16FinancialIndex'),delta),len(AMOUNTS)),len(AMOUNTS)))
                a.do(P(T('S16FinancialControl'),'mcToggle'),'setIndexByValue',T('S16FinancialIndex'));a.ret()
            return change_body
        a.when(('bin',16,own,EQ(R(2),P(G('INPUTCODE'),'UI_LEFT'))),change(-1))
        a.when(('bin',16,own,EQ(R(2),P(G('INPUTCODE'),'UI_RIGHT'))),change(1))
        # Enter on a toggle cannot start a new career. Only the original
        # first-row Advance action can arm the selected amount.
        a.when(('bin',16,own,EQ(R(2),P(G('INPUTCODE'),'ADVANCE'))),lambda a:a.ret())
        a.when(('bin',16,EQ(T('S16SelectedRow'),0),EQ(R(2),P(G('INPUTCODE'),'ADVANCE'))),lambda a:(
            a.set(R(1),'S16FinancialAccepted',True),send(a,'ARM',index(('array',AMOUNTS),T('S16FinancialIndex')))))
        a.when(EQ(R(2),P(G('INPUTCODE'),'BACK')),lambda a:(a.set(R(1),'S16FinancialAccepted',False),send(a,'CANCEL')))
        a.ret(CALL(R(1),'S16Base_LocalEventHandler',R(2),R(3)))
    a.function('_LocalEventHandler',2,event)
    a.function('_OnExitScreen',0,lambda a:(a.when(EQ(T('S16FinancialAccepted'),False),lambda a:send(a,'CANCEL')),a.do(R(1),'S16Base_OnExitScreen')))
    a.label(installed);a.op(0);a.finish()
    const=next(e for e in big.entries.values() if e.data[:4]==b'Apt1' or e.data[:17]==b'Apt constant file')
    root=Reader(const.data,20,apt.width).ptr();reader,_=apt.header(root);reader.i();frames=reader.ptr()
    count,table=struct.unpack_from('<I4xQ',data,frames);redirected=False
    for i in range(count):
        at=struct.unpack_from('<Q',data,table+8*i)[0]
        if struct.unpack_from('<i',data,at)[0]==8 and struct.unpack_from('<i',data,at+8)[0]==registration[1] and struct.unpack_from('<Q',data,at+16)[0]==registration[-1]:
            struct.pack_into('<Q',data,at+16,start);redirected=True
    if not redirected:raise ValueError('Original Setup registration not found')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);write_native_big(big,output)
    return dict(schema=1,path=UI_PATH,amounts=AMOUNTS,sha256=hashlib.sha256(output.read_bytes()).hexdigest(),original_rows_preserved=True)
