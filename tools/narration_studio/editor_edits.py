"""Persist transcript and user classification edits in the existing catalog."""
from pathlib import Path
from atomic_io import write_text
from topics import topic

def update_transcript(db,table,key,text):
    if table not in ('clips','sources'):raise ValueError('Tipo de áudio inválido.')
    row=db.execute('SELECT * FROM '+table+' WHERE key=?',(key,)).fetchone()
    if row is None:raise ValueError('Áudio não encontrado.')
    path=row['wav'] if table=='clips' else row['path']
    if table=='clips':db.execute('UPDATE clips SET transcript=? WHERE wav=?',(text,path))
    else:db.execute('UPDATE sources SET transcript=?,confidence=0,topic=CASE WHEN topic_manual=1 THEN topic ELSE ? END WHERE key=?',(text,topic(row['event'],path,text),key))
    write_text(Path(str(path)+'.txt'),text)

def update_style(db,key,value):
    row=db.execute('SELECT * FROM sources WHERE key=?',(key,)).fetchone()
    if row is None:raise ValueError('Áudio não encontrado.')
    value=value.strip()
    manual=bool(value and value!='(automático)')
    style=value if manual else topic(row['event'],row['path'],row['transcript'] or '')
    if len(style)>120:raise ValueError('O nome do estilo deve ter até 120 caracteres.')
    db.execute('UPDATE sources SET topic=?,topic_manual=? WHERE key=?',(style,int(manual),key))
    return style
