"""Idempotent, state-local view refresh; keep the native settings controller."""
import json
from pathlib import Path

EVENT='Server16RefreshGameSettings'
VIEW='game/screens/settings/GameSettings'

def refresh_actions():
    return [['unloadView',['screen',VIEW]],['loadView',['screen',VIEW,'','']]]

def patch(path):
    path=Path(path);data=json.loads(path.read_text(encoding='utf-8-sig'));found=[]
    def visit(node):
        if isinstance(node,list):
            for item in node:visit(item)
        elif isinstance(node,dict):
            if node.get('name') in ('SettingsGame','GameSettings') and any(
                isinstance(row,list) and row and row[0]=='loadView' and VIEW in row[1]
                for row in node.get('onEnter',[])):
                transitions=node.setdefault('transitions',[])
                entry={'event':EVENT,'actions':refresh_actions()}
                existing=next((t for t in transitions if t.get('event')==EVENT),None)
                if existing is None:transitions.append(entry)
                elif existing!=entry:raise ValueError('A transição de opções pertence a outra revisão')
                found.append(node['name'])
            for key,value in node.items():
                if key!='transitions':visit(value)
    visit(data)
    if not found:raise ValueError('Estado nativo de opções não encontrado')
    text=json.dumps(data,ensure_ascii=False,indent=2)+'\n';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf8')
    return found
