"""Collapsible audio library. Database reads and folder scans never block Tk."""
from pathlib import Path
import json,queue,threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from core import connect,import_sources,copy_audio_collection,remove_source_asset,WORK,USER_AUDIO_ROOT,FFMPEG
from audio_playback import AudioPlayer
from projects import folder as project_folder,safe_name
from topics import TOPICS

class LibraryPanel(ttk.Frame):
    def __init__(self,pane,studio):
        super().__init__(pane,padding=(8,0,0,0));self.studio=studio
        self.results=queue.Queue();self.copy_progress=queue.Queue();self.generation=0;self.rows={};self.offset=0;self.total=0;self.refresh_timer=None
        self.query=tk.StringVar();self.filter=tk.StringVar(value='Todos');self.info=tk.StringVar(value='Adicione uma pasta de áudios à biblioteca deste narrador.')
        self.columnconfigure(0,weight=1);self.rowconfigure(7,weight=1)
        self.heading=ttk.Label(self,font=('Segoe UI',14,'bold'))
        self.heading.grid(row=0,column=0,sticky='w',pady=6)
        actions=ttk.Frame(self);actions.grid(row=1,column=0,sticky='ew')
        ttk.Button(actions,text='＋ Importar pasta inteira…',command=self.attach).pack(side='left')
        self.transcribe_one_button=ttk.Button(actions,text='Transcrever áudio selecionado',command=self.transcribe_selected,state='disabled')
        self.transcribe_one_button.pack(side='left',padx=4)
        batch=ttk.Frame(self);batch.grid(row=2,column=0,sticky='w',pady=(3,0))
        ttk.Button(batch,text='Transcrever áudios sem transcrição',command=self.transcribe).pack(side='left')
        self.remove_button=ttk.Button(batch,text='Remover asset selecionado',command=self.remove_selected,state='disabled')
        self.remove_button.pack(side='left',padx=5)
        self.help=ttk.Label(self,wraplength=440,justify='left')
        self.help.grid(row=3,column=0,sticky='w',pady=(3,0))
        self.progress=ttk.Progressbar(self,mode='determinate',maximum=100)
        self.progress.grid(row=4,column=0,sticky='ew',pady=5)
        filters=ttk.Frame(self);filters.grid(row=5,column=0,sticky='ew',pady=4)
        ttk.Label(filters,text='⌕').pack(side='left',padx=(0,4))
        ttk.Entry(filters,textvariable=self.query).pack(side='left',fill='x',expand=True)
        ttk.Label(filters,text='Filtrar:').pack(side='left',padx=(5,2))
        combo=ttk.Combobox(filters,textvariable=self.filter,values=['Todos','Ainda não usados','Já usados','Sem transcrição'],state='readonly',width=18)
        combo.pack(side='left',padx=4);combo.bind('<<ComboboxSelected>>',lambda e:self.refresh(reset=True))
        self.query.trace_add('write',lambda *_:self.schedule())
        organization=ttk.Frame(self);organization.grid(row=6,column=0,sticky='ew',pady=(0,4))
        self.style_filter=tk.StringVar(value='Todos os estilos')
        self.grouping=tk.StringVar(value='Sem grupos')
        self.sort_by=tk.StringVar(value='Nome A–Z')
        ttk.Label(organization,text='Estilo:').pack(side='left',padx=(0,3))
        styles=ttk.Combobox(organization,textvariable=self.style_filter,values=['Todos os estilos',*TOPICS],state='readonly',width=20)
        styles.pack(side='left');styles.bind('<<ComboboxSelected>>',lambda e:self.refresh(reset=True))
        ttk.Label(organization,text='Agrupar:').pack(side='left',padx=(5,3))
        groups=ttk.Combobox(organization,textvariable=self.grouping,values=['Sem grupos','Por estilo'],state='readonly',width=11)
        groups.pack(side='left');groups.bind('<<ComboboxSelected>>',lambda e:self.refresh(reset=True))
        ttk.Label(organization,text='Ordem:').pack(side='left',padx=(5,3))
        ordering=ttk.Combobox(organization,textvariable=self.sort_by,values=['Nome A–Z','Estilo','Mais usados','Menos usados'],state='readonly',width=13)
        ordering.pack(side='left');ordering.bind('<<ComboboxSelected>>',lambda e:self.refresh(reset=True))
        body=ttk.Frame(self);body.grid(row=7,column=0,sticky='nsew')
        self.tree=ttk.Treeview(body,columns=('audio','uses','text'),show='headings',selectmode='browse')
        for column,title,width in [('audio','Estilo / arquivo',190),('uses','Uso',60),('text','Transcrição',220)]:
            self.tree.heading(column,text=title);self.tree.column(column,width=width,minwidth=60)
        scroll=ttk.Scrollbar(body,command=self.tree.yview);self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self.player=AudioPlayer(self,'Ouvir áudio da biblioteca',WORK/'preview_cache',FFMPEG,studio.pause_other,studio.status.set)
        studio.players.append(self.player);self.player.grid(row=8,column=0,sticky='ew',pady=6)
        self.tree.bind('<<TreeviewSelect>>',self.select_asset)
        self.tree.bind('<Double-1>',lambda e:self.use())
        ttk.Button(self,text='Aplicar à fala selecionada ←',command=self.use).grid(row=9,column=0,sticky='ew',pady=6)
        nav=ttk.Frame(self);nav.grid(row=10,column=0,sticky='ew')
        ttk.Button(nav,text='←',command=lambda:self.page(-200)).pack(side='left')
        ttk.Button(nav,text='→',command=lambda:self.page(200)).pack(side='left',padx=4)
        ttk.Label(nav,textvariable=self.info,wraplength=420).pack(side='left',fill='x',expand=True)
        self.after(100,self.poll)

    def selected(self):
        selection=self.tree.selection();return self.rows.get(selection[0]) if selection else None

    def select_asset(self,event=None):
        row=self.selected()
        self.player.set_source((row or {}).get('path'))
        self.transcribe_one_button.configure(state='normal' if row else 'disabled')
        self.remove_button.configure(state='normal' if row else 'disabled')

    def schedule(self):
        if self.refresh_timer:self.after_cancel(self.refresh_timer)
        self.refresh_timer=self.after(250,lambda:self.refresh(reset=True))

    def refresh(self,reset=False):
        if reset:self.offset=0
        self.generation+=1;generation=self.generation;name=self.studio.profile.get()
        self.heading.configure(text='Biblioteca de áudio · '+name)
        base=USER_AUDIO_ROOT/safe_name(name)
        self.help.configure(text=f'Base exclusiva de {name}: {base}. Escolha uma pasta e todos os áudios compatíveis, inclusive subpastas, entram aqui.')
        query=self.query.get();state=self.filter.get();offset=self.offset;style=self.style_filter.get();grouping=self.grouping.get();sort_by=self.sort_by.get()
        self.info.set('Carregando biblioteca…')
        def read():
            db=None
            try:
                db=connect()
                db.execute('CREATE TEMP TABLE source_usage(source TEXT PRIMARY KEY,uses INTEGER)')
                db.execute('INSERT INTO source_usage SELECT source,count(DISTINCT clip) FROM mappings WHERE profile=? GROUP BY source',(name,))
                where='s.narrator=?';params=[name]
                if style!='Todos os estilos':where+=' AND s.topic=?';params.append(style)
                if query:where+=' AND (fold(s.path) LIKE fold(?) OR fold(s.transcript) LIKE fold(?) OR fold(s.event) LIKE fold(?) OR fold(s.topic) LIKE fold(?))';params+=['%'+query+'%']*4
                if state=='Ainda não usados':where+=' AND coalesce(u.uses,0)=0'
                elif state=='Já usados':where+=' AND coalesce(u.uses,0)>0'
                elif state=='Sem transcrição':where+=" AND coalesce(s.transcript,'')=''"
                sql=' FROM sources s LEFT JOIN source_usage u ON s.key=u.source WHERE '+where
                total=db.execute('SELECT count(*)'+sql,params).fetchone()[0]
                if grouping=='Por estilo' or sort_by=='Estilo':order='s.topic COLLATE NOCASE,s.path COLLATE NOCASE'
                elif sort_by=='Mais usados':order='coalesce(u.uses,0) DESC,s.path COLLATE NOCASE'
                elif sort_by=='Menos usados':order='coalesce(u.uses,0),s.path COLLATE NOCASE'
                else:order='s.path COLLATE NOCASE'
                rows=[dict(r) for r in db.execute('SELECT s.*,coalesce(u.uses,0) uses'+sql+' ORDER BY '+order+' LIMIT 200 OFFSET ?',params+[offset])]
                self.results.put((generation,rows,total,None))
            except Exception as exc:self.results.put((generation,[],0,str(exc)))
            finally:
                if db:db.close()
        threading.Thread(target=read,daemon=True).start()

    def poll(self):
        if self.studio.closed:return
        try:
            while True:
                done,total=self.copy_progress.get_nowait()
                self.progress.configure(maximum=max(1,total),value=done)
                self.info.set(f'Copiando áudios para a biblioteca… {done:,} / {total:,}')
        except queue.Empty:pass
        try:
            while True:
                generation,rows,total,error=self.results.get_nowait()
                if generation!=self.generation:continue
                if error:self.info.set(error);continue
                self.total=total;self.rows={r['key']:r for r in rows};self.tree.delete(*self.tree.get_children())
                last_style=None
                for r in rows:
                    if self.grouping.get()=='Por estilo' and r['topic']!=last_style:
                        group_id=f"group:{generation}:{len(self.tree.get_children())}"
                        self.tree.insert('','end',iid=group_id,values=('── '+(r['topic'] or 'Outros comentários')+' ──','',''))
                        last_style=r['topic']
                    filename=Path(r['path']).name
                    label=(r['topic']+' · ' if self.grouping.get()!='Por estilo' and self.sort_by.get()!='Estilo' else '')+filename
                    self.tree.insert('','end',iid=r['key'],values=(label,'✓ '+str(r['uses'])+'×' if r['uses'] else 'Disponível',r['transcript'] or '[Pendente]'))
                page=self.offset//200+1;pages=max(1,(total+199)//200)
                first=f'{self.offset+1:,}'.replace(',','.') if rows else '0'
                last=f'{self.offset+len(rows):,}'.replace(',','.')
                count=f'{total:,}'.replace(',','.')
                self.info.set(f'Página {page} de {pages} · áudios {first}–{last} de {count}')
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
        selected=filedialog.askdirectory(title='Escolha uma pasta de áudios · '+name)
        if not selected:return
        folder=str(Path(selected).expanduser().resolve())
        managed=USER_AUDIO_ROOT/safe_name(name)
        self.info.set('Copiando os áudios para a biblioteca organizada…')
        self.progress['value']=0
        def task():
            library,count=copy_audio_collection(folder,managed,progress=lambda done,total:self.copy_progress.put((done,total)))
            if not count:
                return 'Nenhum áudio compatível foi encontrado nessa pasta. Formatos aceitos: WAV, MP3, FLAC, OGG e M4A.'
            indexed=import_sources(name,library)
            path=project_folder(name)/'library_folders.json';path.parent.mkdir(parents=True,exist_ok=True)
            folders=[str(Path(item).expanduser().resolve()) for item in json.loads(path.read_text(encoding='utf8'))] if path.exists() else []
            library=str(Path(library).resolve())
            if library not in folders:folders.append(library)
            path.write_text(json.dumps(folders,ensure_ascii=False,indent=2),encoding='utf8')
            from projects import save
            save(name)
            found=f'{indexed:,}'.replace(',','.')
            return f'Biblioteca de {name} atualizada: {found} áudios disponíveis em {library}. Eles já aparecem na lista para ouvir e associar.'
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

    def transcribe_selected(self):
        row=self.selected();name=self.studio.profile.get()
        if not row:return
        if name=='Tiago Leifert':
            messagebox.showinfo('Transcrição','Selecione um narrador personalizado para transcrever assets.',parent=self)
            return
        if row.get('transcript') and not messagebox.askyesno(
            'Refazer transcrição',
            'Este áudio já tem transcrição. Quer substituí-la pela nova transcrição da IA?',
            parent=self,
        ):
            return
        key=row['key']
        self.studio.job(lambda:self.studio.run_worker(['--table','sources','--key',key,'--project',name]))

    def remove_selected(self):
        row=self.selected();name=self.studio.profile.get()
        if not row:return
        path=Path(row['path']).expanduser().resolve()
        managed=(USER_AUDIO_ROOT/safe_name(name)).resolve()
        try:path.relative_to(managed);delete_file=True
        except ValueError:delete_file=False
        action='O arquivo e suas transcrições também serão apagados da pasta de assets deste narrador.' if delete_file else 'O arquivo de áudio original será mantido; somente o asset e suas associações sairão do Studio.'
        uses=row.get('uses',0)
        if not messagebox.askyesno(
            'Remover asset',
            f'Remover “{path.name}” da base de {name}? Ele está associado a {uses} falas desta narração. As associações existentes serão removidas. {action}',
            parent=self,
        ):
            return
        self.player.pause();self.studio.right_player.pause()
        key=row['key']
        def task():
            result=remove_source_asset(name,key,managed)
            from projects import save
            for profile in result['profiles']:save(profile)
            if result['delete_error']:return f'Asset removido do catálogo, mas não consegui apagar o arquivo: {result["delete_error"]}'
            detail='O arquivo e a transcrição foram apagados.' if result['deleted_file'] else 'O áudio original em disco foi preservado.'
            return f'Asset removido da base de {name}. {detail} {len(result["profiles"])} narradores tiveram suas associações atualizadas.'
        self.studio.job(task)
