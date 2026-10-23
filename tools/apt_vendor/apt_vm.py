"""Small, bounded ActionScript evaluator for display setup in FIFA APTs.

Only in-memory objects and explicitly supplied display callbacks are accessible.
It has no file, network, Python eval or shell primitives.
"""
from dataclasses import dataclass
import math
from apt_actions import RegisterValue,source_number

class Unknown:
    def __repr__(self):return 'UnknownDisplayMetric'
UNKNOWN=Unknown()

class Object:
    def __init__(self,values=None,prototype=None):self.values=values or {};self.prototype=prototype
    def get(self,key):
        if key in self.values:return self.values[key]
        return self.prototype.get(key) if self.prototype else None
    def set(self,key,value):self.values[key]=value
    def __repr__(self):return 'Object('+','.join(map(str,list(self.values)[:8]))+')'

class Function(Object):
    def __init__(self,meta,body,scope):
        super().__init__({'prototype':Object()});self.meta=meta;self.body=body;self.scope=scope
    def __repr__(self):return f'Function({self.meta.get("name") or self.meta.get("start")})'

@dataclass
class Native:
    name:str

def text(value):
    if value is None:return 'undefined'
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,float) and value.is_integer():return str(int(value))
    if isinstance(value,list):return ','.join('' if v is None else text(v) for v in value)
    return str(value)

def number(value):
    if isinstance(value,Unknown):return value
    if value is None:return 0.
    try:return float(value)
    except (ValueError,TypeError):return 0.

class VM:
    def __init__(self,callback=None):
        self.global_=Object();self.callback=callback;self.steps=0;self.depth=0;self.errors=[];self.unknown=set()
        for key in ('Object','Array','MovieClip','TextFormat','Color','String','Number'):
            self.global_.set(key,Native(key))
        self.global_.set('_global',self.global_);self.global_.set('Math',Object({k:Native('Math.'+k) for k in ('round','ceil','floor','abs','max','min')}))
        self.global_.set('ASSetPropFlags',Native('ignore'))

    def get(self,obj,key):
        if isinstance(key,float) and key.is_integer():key=int(key)
        if isinstance(obj,Object):return obj.get(key)
        if isinstance(obj,(str,list,tuple)):
            if key=='length':return len(obj)
            if isinstance(key,(int,float)) or str(key).isdigit():
                index=int(key);return obj[index] if 0<=index<len(obj) else None
            if key in ('split','charAt','toUpperCase','toLowerCase','substr','substring','push','join'):
                return Native(key)
        if isinstance(obj,Native):
            if key=='prototype':return None
            return Native(obj.name+'.'+str(key))
        return None

    def set(self,obj,key,value):
        if isinstance(key,float) and key.is_integer():key=int(key)
        if isinstance(obj,Object):obj.set(key,value)
        elif isinstance(obj,list):
            try:index=int(key)
            except (ValueError,TypeError):return
            if not 0<=index<10000:return
            obj.extend([None]*max(0,index+1-len(obj)));obj[index]=value

    def path(self,path,scope=None):
        parts=str(path).split('.');value=(scope or self.global_).get(parts[0])
        if value is None:value=self.global_.get(parts[0])
        for key in parts[1:]:value=self.get(value,key)
        return value

    def invoke(self,function,owner,args=()):
        if isinstance(function,tuple) and len(function)==2:
            return self.invoke(function[1],function[0],args)
        if isinstance(function,Function):
            if self.depth>=32:raise RuntimeError('Limite de chamadas APT.')
            self.depth+=1
            try:
                scope=Object({'this':owner,'arguments':list(args)},function.scope)
                regs={};reg=1;flags=function.meta.get('flags',0)
                for flag,value in ((1,owner),(4,list(args)),(16,None),(64,None),(128,None),(256,self.global_)):
                    if flags&flag:regs[reg]=value;reg+=1
                for index,(slot,name) in enumerate(function.meta.get('params',[])):
                    value=args[index] if index<len(args) else None
                    scope.set(name,value)
                    if slot:regs[slot]=value
                return self.run(function.body,scope,owner,regs)
            finally:self.depth-=1
        if isinstance(function,Native):
            name=function.name
            if name=='ignore' or name.endswith('registerClass'):return None
            if name in ('Object','MovieClip'):return Object()
            if name=='Array':return list(args)
            if name=='String':return text(args[0]) if args else ''
            if name=='Number':return number(args[0]) if args else 0
            if name=='TextFormat':return Object(dict(zip(('font','size','color','bold','italic','underline','url','target','align','leftMargin','rightMargin','indent','leading'),args)))
            if name in ('Color',):return Object({'target':args[0] if args else None,'setTransform':Native('colorTransform')})
            if name.startswith('Math.'):
                values=[number(v) for v in args];fn=name.split('.')[-1]
                return {'round':round,'ceil':math.ceil,'floor':math.floor,'abs':abs,'max':max,'min':min}[fn](*values) if values else 0
            if name=='split':return text(owner).split(text(args[0]))
            if name=='charAt':return owner[int(number(args[0])):int(number(args[0]))+1]
            if name=='toUpperCase':return text(owner).upper()
            if name=='toLowerCase':return text(owner).lower()
            if name in ('substr','substring'):
                start=int(number(args[0]));end=int(number(args[1])) if len(args)>1 else len(owner)
                return owner[start:start+end if name=='substr' else end]
            if name=='join':return text(args[0] if args else ',').join(map(text,owner))
            if name=='push':owner.extend(args);return len(owner)
            if self.callback:return self.callback(name,owner,args)
        return None

    def method(self,obj,name,args):
        if name is None and isinstance(obj,(Function,Native,tuple)):
            return self.invoke(obj,None,args)
        function=self.get(obj,name)
        if function is None and self.callback:return self.callback(str(name),obj,args)
        return self.invoke(function,obj,args)

    def run(self,code,scope=None,owner=None,regs=None):
        scope=scope or self.global_;regs=regs or {};stack=[];index=0;locations={i.offset:n for n,i in enumerate(code)}
        def pop():return stack.pop() if stack else None
        def arguments():
            count=int(number(pop()))
            if not 0<=count<=10000:raise RuntimeError('Argumentos APT inválidos.')
            return [pop() for _ in range(count)]
        while index<len(code):
            self.steps+=1
            if self.steps>150000:raise RuntimeError('Limite de execução APT.')
            i=code[index];index+=1;op=i.op;v=i.value
            if op==0:break
            if op in (136,7,6,38,186):
                if op==38:pop()
                continue
            if op in (161,162,163,180,183):stack.append(v)
            elif op in (181,182):
                bits=8 if op==181 else 16;value=int(v)-(1<<bits) if v>=1<<(bits-1) else int(v)
                stack.append(source_number(value,v.source) if hasattr(v,'source') else value)
            elif op==150:stack.extend(regs.get(item.index) if isinstance(item,RegisterValue) else item for item in v)
            elif op==185:stack.append(regs.get(v))
            elif op in (86,112):stack.append(owner)
            elif op in (88,113):stack.append(self.global_)
            elif op in (89,90,115,116,117,118):stack.append({89:0,90:1,115:True,116:False,117:None,118:None}[op])
            elif op in (142,155):stack.append(Function(v,i.body,scope))
            elif op==135:regs[v]=stack[-1] if stack else None
            elif op==23:pop()
            elif op==76:stack.append(stack[-1] if stack else None)
            elif op==77:a=pop();b=pop();stack.extend((a,b))
            elif op in (28,164,174):stack.append(self.path(pop() if op==28 else v,scope))
            elif op==78:key=pop();stack.append(self.get(pop(),key))
            elif op in (165,175):
                value=self.get(pop(),v)
                if i.number_source and isinstance(value,(int,float)) and not hasattr(value,'source'):value=source_number(float(value),i.number_source)
                stack.append(value)
            elif op==58:
                key=pop();obj=pop()
                if isinstance(obj,Object):obj.values.pop(key,None)
                elif isinstance(obj,list) and isinstance(key,(int,float)) and 0<=int(key)<len(obj):obj[int(key)]=None
                stack.append(True)
            elif op==79:value=pop();key=pop();self.set(pop(),key,value)
            elif op==167:value=pop();self.set(pop(),v,value)
            elif op in (29,60,166,114):
                value=0 if op==114 else pop();key=pop() if op in (29,60,114) else v;scope.set(key,value)
            elif op==65:scope.set(pop(),None)
            elif op in (61,91,92,176,177):
                name=pop() if op in (61,91,92) else v;args=arguments();value=self.invoke(self.path(name,scope),owner,args)
                if op in (92,177):scope.set(pop(),value)
                elif op==61:stack.append(value)
            elif op in (82,93,94,178,179):
                name=pop() if op in (82,93,94) else v;obj=pop();args=arguments();value=self.method(obj,name,args)
                if op in (94,179):scope.set(pop(),value)
                elif op==82:stack.append(value)
            elif op==64:
                name=pop();args=arguments();fn=self.path(name,scope)
                if isinstance(fn,Function):obj=Object(prototype=fn.get('prototype'));self.invoke(fn,obj,args);stack.append(obj)
                else:stack.append(self.invoke(fn,None,args))
            elif op==66:stack.append(arguments())
            elif op==67:
                count=int(number(pop()));obj=Object()
                if not 0<=count<10000:raise RuntimeError('Objeto APT inválido.')
                for _ in range(count):value=pop();key=pop();obj.set(key,value)
                stack.append(obj)
            elif op==105:
                parent=pop();child=pop()
                if isinstance(child,Object):child.get('prototype').prototype=self.get(parent,'prototype')
            elif op==43:
                value=pop();constructor=pop()
                # Typed MovieClip casts do not create a new display instance.
                stack.append(value if isinstance(value,Object) else None)
            elif op==44:
                constructor=pop();interfaces=arguments()
                if isinstance(constructor,Object):constructor.set('__interfaces',interfaces)
            elif op in (129,140,159):
                frame=v+1 if op==129 else v if op==140 else pop()
                if owner is not None and self.callback:self.callback('gotoAndStop',owner,[frame])
            elif op in (153,157,184):
                condition=None if op==153 else pop()
                if isinstance(condition,Unknown):return None
                take=True if op==153 else bool(condition) if op==157 else not bool(condition)
                if take:
                    if v not in locations:break
                    index=locations[v]
            elif op==62:return pop()
            elif op==18:stack.append(not bool(pop()))
            elif op in (24,74):
                value=pop();stack.append(value if op==74 and isinstance(value,(int,float)) else number(value))
            elif op==75:stack.append(text(pop()))
            elif op==80:stack.append(number(pop())+1)
            elif op==81:stack.append(number(pop())-1)
            elif op==68:stack.append('undefined' if pop() is None else 'object')
            elif op in (10,11,12,13,14,15,16,17,19,33,63,71,72,73,96,97,98,99,100,101,102,103):
                b=pop();a=pop()
                if isinstance(a,Unknown) or isinstance(b,Unknown):stack.append(UNKNOWN);continue
                if op in (10,71,33):value=text(a)+text(b) if op==33 or isinstance(a,str) or isinstance(b,str) else number(a)+number(b)
                elif op==11:value=number(a)-number(b)
                elif op==12:value=number(a)*number(b)
                elif op==13:value=number(a)/number(b) if number(b) else 0
                elif op in (14,19,73,102):value=a==b or a is None and b is None
                elif op in (15,72):value=number(a)<number(b)
                elif op==103:value=number(a)>number(b)
                elif op==16:value=bool(a) and bool(b)
                elif op==17:value=bool(a) or bool(b)
                elif op==63:value=number(a)%number(b) if number(b) else 0
                else:
                    a,b=int(number(a)),int(number(b));value={96:lambda:a&b,97:lambda:a|b,98:lambda:a^b,99:lambda:a<<(b&31),100:lambda:a>>(b&31),101:lambda:(a&0xffffffff)>>(b&31)}[op]()
                stack.append(value)
            else:raise RuntimeError(f'Opcode APT non exécuté {op:02X} em {i.offset:X}')
        return None
