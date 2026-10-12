"""Collapsible audio library. Database reads and folder scans never block Tk."""
from pathlib import Path
import json,queue,threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from core import connect,import_sources,WORK,PROJECTS,FFMPEG
from audio_playback import AudioPlayer

class LibraryPanel(ttk.Frame):
    def __init__(self,pane,studio):
        super().__init__(pane,padding=(8,0,0,0));self.studio=studio
        self.results=queue.Queue();self.generation=0;self.rows={};self.offset=0;self.total=0;self.refresh_timer=None
        self.query=tk.StringVar();self.filter=tk.StringVar(value='Todos');self.info=tk.StringVar(value='Anexe uma pasta de áudios deste narrador.')
        self.columnconfigure(0,weight=1);self.rowconfigure(4,weight=1)
        ttk.Label(self,text='Biblioteca de áudios',font=('Segoe UI',14,'bold')).grid(row=0,column=0,sticky='w',pady=6)
        actions=ttk.Frame(self);actions.grid(row=1,column=0,sticky='ew')
        ttk.Button(actions,text='Anexar pasta',command=self.attach).pack(side='left')
        ttk.Button(actions,text='Transcrever pasta com IA',command=self.transcribe).pack(side='left',padx=4)
        self.progress=ttk.Progressbar(self,mode='determinate',maximum=100)
        self.progress.grid(row=2,column=0,sticky='ew',pady=5)
        filters=ttk.Frame(self);filters.grid(row=3,column=0,sticky='ew',pady=4)
        ttk.Entry(filters,textvariable=self.query).pack(side='left',fill='x',expand=True)
        combo=ttk.Combobox(filters,textvariable=self.filter,values=['Todos','Ainda não usados','Já usados','Sem transcrição'],state='readonly',width=18)
        combo.pack(side='left',padx=4);combo.bind('<<ComboboxSelected>>',lambda e:self.refresh(reset=True))
        self.query.trace_add('write',lambda *_:self.schedule())
        body=ttk.Frame(self);body.grid(row=4,column=0,sticky='nsew')
        self.tree=ttk.Treeview(body,columns=('audio','uses','text'),show='headings',selectmode='browse')
        for column,title,width in [('audio','Arquivo',160),('uses','Uso',80),('text','Transcrição',220)]:
            self.tree.heading(column,text=title);self.tree.column(column,width=width,minwidth=60)
        scroll=ttk.Scrollbar(body,command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.player=AudioPlayer(self,'Ouvir áudio da biblioteca',WORK/'preview_cache',FFMPEG,studio.pause_other,studio.status.set)
        studio.players.append(self.player);self.player.grid(row=5,column=0,sticky='ew',pady=6)
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.player.set_source((self.selected() or {}).get('path')))
        self.tree.bind('<Double-1>',lambda e:self.use())
        ttk.Button(self,text='Aplicar à fala selecionada ←',command=self.use).grid(row=6,column=0,sticky='ew',pady=6)
        nav=ttk.Frame(self);nav.grid(row=7,column=0,sticky='ew')
        ttk.Button(nav,text='←',command=lambda:self.page(-200)).pack(side='left')
        ttk.Button(nav,text='→',command=lambda:self.page(200)).pack(side='left',padx=4)
        ttk.Label(nav,textvariable=self.info,wraplength=420).pack(side='left',fill='x',expand=True)
        self.after(100,self.poll)

    def selected(self):
        selection=self.tree.selection();return self.rows.get(selection[0]) if selection else None

    def schedule(self):
        if self.refresh_timer:self.after_cancel(self.refresh_timer)
        self.refresh_timer=self.after(250,lambda:self.refresh(reset=True))

    def refresh(self,reset=False):
        if reset:self.offset=0
        self.generation+=1;generation=self.generation;name=self.studio.profile.get()
        query=self.query.get();state=self.filter.get();offset=self.offset
        self.info.set('Carregando biblioteca…')
        def read():
            db=None
            try:
                db=connect()
                db.execute('CREATE TEMP TABLE source_usage(source TEXT PRIMARY KEY,uses INTEGER)')
                db.execute('INSERT INTO source_usage SELECT source,count(DISTINCT clip) FROM mappings WHERE profile=? GROUP BY source',(name,))
                where='s.narrator=?';params=[name]
                if query:where+=' AND (fold(s.path) LIKE fold(?) OR fold(s.transcript) LIKE fold(?))';params+=['%'+query+'%']*2
                if state=='Ainda não usados':where+=' AND coalesce(u.uses,0)=0'
                elif state=='Já usados':where+=' AND coalesce(u.uses,0)>0'
                elif state=='Sem transcrição':where+=" AND coalesce(s.transcript,'')=''"
                sql=' FROM sources s LEFT JOIN source_usage u ON s.key=u.source WHERE '+where
                total=db.execute('SELECT count(*)'+sql,params).fetchone()[0]
                rows=[dict(r) for r in db.execute('SELECT s.*,coalesce(u.uses,0) uses'+sql+' ORDER BY s.path LIMIT 200 OFFSET ?',params+[offset])]
                self.results.put((generation,rows,total,None))
            except Exception as exc:self.results.put((generation,[],0,str(exc)))
            finally:
                if db:db.close()
        threading.Thread(target=read,daemon=True).start()

    def poll(self):
        if self.studio.closed:return
        try:
            while True:
                generation,rows,total,error=self.results.get_nowait()
                if generation!=self.generation:continue
                if error:self.info.set(error);continue
                self.total=total;self.rows={r['key']:r for r in rows};self.tree.delete(*self.tree.get_children())
                for r in rows:self.tree.insert('','end',iid=r['key'],values=(Path(r['path']).name,'✓ '+str(r['uses'])+'×' if r['uses'] else 'Disponível',r['transcript'] or '[Pendente]'))
                self.info.set(str(self.offset+1 if rows else 0)+'–'+str(self.offset+len(rows))+' / '+str(total)+' áudios')
        except queue.Empty:pass
        progress=WORK/('library_progress_'+self.studio.profile.get()+'.json')
        try:
            state=json.loads(progress.read_text(encoding='utf8'));self.progress['value']=100*state['done']/max(1,state['total'])
        except (OSError,ValueError,KeyError):pass
        self.after(200,self.poll)

    def page(self,delta):
        offset=max(0,self.offset+delta)
        if offset<self.total or offset==0:self.offset=offset;self.refresh()

    def attach(self):
        name=self.studio.profile.get()
        if name=='Tiago Leifert':messagebox.showinfo('Biblioteca','Crie ou selecione um narrador personalizado.');return
        folder=filedialog.askdirectory(title='Pasta dos áudios completos · '+name)
        if not folder:return
        def task():
            import_sources(name,folder)
            path=PROJECTS/name/'library_folders.json';path.parent.mkdir(parents=True,exist_ok=True)
            folders=json.loads(path.read_text(encoding='utf8')) if path.exists() else []
            if folder not in folders:folders.append(folder)
            path.write_text(json.dumps(folders,ensure_ascii=False,indent=2),encoding='utf8')
            return 'Pasta anexada. Abra a biblioteca para escolher os áudios.'
        self.studio.job(task)

    def use(self):
        row=self.selected();name=self.studio.profile.get();clip=self.studio.current_key
        if not row or not clip:return
        self.studio.save_visible_texts()
        def task():
            from profiles import assign
            from projects import save
            assign(name,clip,row['key']);save(name)
            return 'Áudio aplicado à fala selecionada.'
        self.studio.job(task)

    def transcribe(self):
        name=self.studio.profile.get()
        if name=='Tiago Leifert':return
        self.studio.job(lambda:self.studio.run_worker(['--library','--project',name]))
