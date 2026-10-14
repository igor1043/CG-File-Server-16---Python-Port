"""A practical, paired original/custom narration editor."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import threading, queue, subprocess, shutil, hashlib, json,sqlite3
from portable_setup import ensure_game_config
ensure_game_config()
from core import connect, WORK, DB, GAME, APP_ROOT, PROJECTS, USER_AUDIO_ROOT, FFMPEG, CONFIG_PATH, CONFIG, import_sources,RESOURCE_ROOT,CODE_ROOT,SOURCE_ROOT,WHISPER_MODEL
from profiles import assign
from topics import TOPICS, topic
from audio_playback import AudioPlayer
from editor_catalog import paired_page, coverage, converted_keys
import projects
from server16_py.narration_competitions import competitions
from startup_wizard import choose_profile


def startup_checkpoint(stage):
    import sys,time
    if '--smoke' in sys.argv:
        with (APP_ROOT/'studio_startup.log').open('a',encoding='utf8') as log:
            log.write(f'{time.time():.3f} {stage}\n')


def number(value):
    return f'{value:,}'.replace(',', '.')


class Studio(tk.Tk):
    def __init__(self,initial_profile='Vilani'):
        startup_checkpoint('creating-window')
        super().__init__()
        self.title('FIFA 16 · Narration Studio')
        self.geometry('1600x900'); self.minsize(1260,760)
        self.queue=queue.Queue(); self.busy=False; self.offset=0
        self.profile=tk.StringVar(value=initial_profile or 'Vilani')
        self.original_search=tk.StringVar(); self.source_search=tk.StringVar(); self.topic_filter=tk.StringVar(value='Todos os assuntos')
        self.state_filter=tk.StringVar(value='Todos')
        self.status=tk.StringVar(value='Selecione uma linha: original e sua narração ficam na mesma ocorrência.')
        self.progress=tk.StringVar(); self.original_count=tk.StringVar(); self.custom_count=tk.StringVar()
        self.originals={}; self.sources={}; self.current_key=None; self.refresh_job=None; self.loaded_profile=self.profile.get(); self.players=[]
        self.topic_labels={}; self.scrolls={}; self.total_rows=0
        self.data_requests=queue.Queue(maxsize=1);self.data_results=queue.Queue();self.data_generation=0;self.data_loaded=False
        self.conversion_cache={};self.conversion_verifying=set();self.conversion_results=queue.Queue()
        self.counts=dict(total=0,linked=0,converted=0,transcribed=0,topics={});self.converted={}
        self.loaded_profile=self.profile.get();self.closed=False
        self.write_requests=queue.Queue();self.write_results=queue.Queue();self.local_original_text={};self.local_source_text={}
        self.autosave_timer=None;self.autosave_requested=None;self.autosave_running=False;self.autosave_results=queue.Queue()
        style=ttk.Style(self); style.theme_use('clam')
        style.configure('Treeview',rowheight=28,font=('Segoe UI',10))
        style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'))
        style.configure('TButton',padding=6)
        top=ttk.Frame(self,padding=(14,10)); top.pack(fill='x')
        ttk.Label(top,text='FIFA 16 Narration Studio',font=('Segoe UI',21,'bold')).pack(side='left')
        ttk.Button(top,text='Gerar áudio e instalar no jogo',command=self.build_project).pack(side='right')
        bar=ttk.Frame(self,padding=(14,0,14,8)); bar.pack(fill='x')
        ttk.Label(bar,text='Narrador ativo:').pack(side='left',padx=(0,6))
        self.profile_box=ttk.Combobox(bar,textvariable=self.profile,values=projects.names(),width=20,state='readonly')
        self.profile_box.pack(side='left'); self.profile_box.bind('<<ComboboxSelected>>',lambda e:self.change_profile())
        for label,fn in [('Criar narrador',self.new_profile),('Importar projeto…',self.open_project),('Configurar narrador…',self.edit_project)]:
            ttk.Button(bar,text=label,command=fn).pack(side='left',padx=(6,0))
        filters=ttk.Frame(self,padding=(14,0,14,8)); filters.pack(fill='x')
        ttk.Label(filters,text='Tipo de ocorrência (filtra as duas colunas):').pack(side='left',padx=(0,6))
        self.topic_box=ttk.Combobox(filters,textvariable=self.topic_filter,state='readonly',width=38)
        self.topic_box.pack(side='left'); self.topic_box.bind('<<ComboboxSelected>>',lambda e:self.refresh_original())
        ttk.Label(filters,text='Mostrar:').pack(side='left',padx=(10,6))
        states=ttk.Combobox(filters,textvariable=self.state_filter,values=['Todos','Sem áudio próprio','Com áudio próprio','Já convertidos','Ainda não convertidos','Com áudio, a converter','Revisados/aprovados','Sugestões para revisar'],state='readonly',width=22)
        states.pack(side='left'); states.bind('<<ComboboxSelected>>',lambda e:self.refresh_original())
        nav=ttk.Frame(self,padding=(14,0,14,5)); nav.pack(fill='x')
        ttk.Button(nav,text='← Anteriores',command=lambda:self.page(-500)).pack(side='left')
        ttk.Button(nav,text='Próximas →',command=lambda:self.page(500)).pack(side='left',padx=6)
        ttk.Label(nav,textvariable=self.progress).pack(side='left',padx=8)
        ttk.Button(nav,text='← Fala',command=lambda:self.next_occurrence(-1)).pack(side='right')
        ttk.Button(nav,text='Fala →',command=lambda:self.next_occurrence(1)).pack(side='right',padx=6)
        pane=ttk.Panedwindow(self,orient='horizontal'); pane.pack(fill='both',expand=True,padx=14)
        left=ttk.Frame(pane,padding=(0,0,6,0)); right=ttk.Frame(pane,padding=(6,0,0,0))
        pane.add(left,weight=1); pane.add(right,weight=1)
        self.pane=pane
        self.library_panel=None
        self.library_button=ttk.Button(nav,text='Ocultar assets',command=self.toggle_library)
        self.library_button.pack(side='right',padx=6)
        for frame in (left,right):
            frame.columnconfigure(0,weight=1); frame.rowconfigure(3,weight=1)
        ttk.Label(left,text='Original · Tiago Leifert / Caio Ribeiro',font=('Segoe UI',14,'bold')).grid(row=0,column=0,sticky='w',pady=6)
        self.custom_title=ttk.Label(right,text='Sua narração · Vilani',font=('Segoe UI',14,'bold'))
        self.custom_title.grid(row=0,column=0,sticky='w',pady=6)
        ttk.Label(left,textvariable=self.original_count).grid(row=1,column=0,sticky='w',pady=(0,6))
        ttk.Label(right,textvariable=self.custom_count).grid(row=1,column=0,sticky='w',pady=(0,6))
        for frame,label,variable in ((left,'⌕ Buscar original:',self.original_search),(right,'⌕ Buscar narração:',self.source_search)):
            search_bar=ttk.Frame(frame);search_bar.grid(row=2,column=0,sticky='ew',pady=(0,5))
            ttk.Label(search_bar,text=label).pack(side='left',padx=(0,6))
            ttk.Entry(search_bar,textvariable=variable).pack(side='left',fill='x',expand=True)
        self.original_search.trace_add('write',lambda *_:self.schedule_refresh())
        self.source_search.trace_add('write',lambda *_:self.schedule_refresh())
        self.left=self.tree(left,('Fala / ocorrência','Transcrição original'),(210,310),row=3)
        self.right=self.tree(right,('Aprovado','Seu áudio / situação','Sua transcrição'),(70,210,310),columns=('reviewed','name','text'),row=3)
        self.right.tag_configure('approved',background='#ccebd3',foreground='#184b25')
        self.right.bind('<Button-1>',self.review_cell_click,add='+')
        self.left.bind('<<TreeviewSelect>>',lambda e:self.select_row(self.left))
        self.right.bind('<<TreeviewSelect>>',lambda e:self.select_row(self.right))
        self.left_player=AudioPlayer(left,'Ouvir original',WORK/'preview_cache',FFMPEG,self.pause_other,self.status.set)
        self.right_player=AudioPlayer(right,'Ouvir minha narração',WORK/'preview_cache',FFMPEG,self.pause_other,self.status.set)
        self.players=[self.left_player,self.right_player]
        startup_checkpoint('players-ready')
        self.left_player.grid(row=4,column=0,sticky='ew',pady=5)
        self.right_player.grid(row=4,column=0,sticky='ew',pady=5)
        ttk.Label(left,text='Descrição / transcrição original (editável)').grid(row=5,column=0,sticky='w')
        ttk.Label(right,text='Descrição / transcrição da sua narração (editável)').grid(row=5,column=0,sticky='w')
        self.original_text=tk.Text(left,height=4,wrap='word',font=('Segoe UI',11),undo=True)
        self.source_text=tk.Text(right,height=4,wrap='word',font=('Segoe UI',11),undo=True)
        self.original_text.grid(row=6,column=0,sticky='ew',pady=4)
        self.source_text.grid(row=6,column=0,sticky='ew',pady=4)
        lbuttons=ttk.Frame(left); rbuttons=ttk.Frame(right)
        lbuttons.grid(row=7,column=0,sticky='ew',pady=4); rbuttons.grid(row=7,column=0,sticky='ew',pady=4)
        ttk.Button(lbuttons,text='Salvar transcrição',command=self.save_original).grid(row=0,column=0,sticky='w')
        ttk.Button(lbuttons,text='Transcrever este áudio com IA',command=lambda:self.transcribe_selected(True)).grid(row=0,column=1,padx=6,sticky='w')
        self.reference=tk.StringVar(value='Base completa do FIFA 16; nomes e comentários separados por assunto.')
        ttk.Label(lbuttons,textvariable=self.reference,foreground='#68798c').grid(row=1,column=0,columnspan=2,sticky='w',pady=8)
        ttk.Button(rbuttons,text='Salvar transcrição',command=self.save_source).grid(row=0,column=0,sticky='w')
        ttk.Button(rbuttons,text='Transcrever este áudio com IA',command=lambda:self.transcribe_selected(False)).grid(row=0,column=1,padx=6,sticky='w')
        imports=ttk.Frame(rbuttons); imports.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(6,0))
        self.import_button=ttk.Button(imports,text='＋ Importar MP3 / WAV',command=self.import_audio)
        self.import_button.pack(side='left')
        ttk.Button(imports,text='Escolher da biblioteca',command=self.show_library).pack(side='left',padx=6)
        ttk.Button(imports,text='Usar original',command=self.clear_link).pack(side='left')
        review=ttk.Frame(rbuttons);review.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(6,0))
        ttk.Label(review,text='Clique em ☐ na lista para aprovar; a linha aprovada fica verde.').pack(side='left')
        ttk.Button(review,text='Repetir nas variações…',command=self.repeat_variations).pack(side='right',padx=6)
        bottom=ttk.Frame(self,padding=(14,8)); bottom.pack(side='bottom',fill='x',before=pane)
        self.status_label=ttk.Label(bottom,textvariable=self.status,wraplength=1050)
        self.status_label.pack(anchor='w')
        self.status.set('Carregando catálogo… a janela continua disponível.')
        threading.Thread(target=self.data_worker,daemon=True).start()
        threading.Thread(target=self.write_worker,daemon=True).start()
        self.request_data(recount=True);self.after(100,self.poll)
        self.after(30000,self.periodic_coverage)
        self.update_idletasks()
        startup_checkpoint('layout-ready')
        # The action rows have different contents; reserve their common height
        # so both occurrence lists, players and transcripts remain aligned.
        self.column_frames=(left,right)
        for row in (0,1,2,4,5,6,7):
            height=max(frame.grid_bbox(0,row)[3] for frame in self.column_frames)
            for frame in self.column_frames: frame.rowconfigure(row,minsize=height)
        self.protocol('WM_DELETE_WINDOW',self.close_app)
        self.show_library()

    def request_data(self,recount=False):
        self.data_generation+=1
        request=dict(generation=self.data_generation,name=self.profile.get(),original_query=self.original_search.get(),source_query=self.source_search.get(),category=self.category(),
                     offset=self.offset,state=self.state_filter.get(),recount=recount,selected=self.current_key)
        try:self.data_requests.get_nowait()
        except queue.Empty:pass
        self.data_requests.put_nowait(request)

    def data_worker(self):
        cached_name=None;converted={};counts={};cached_converted=None
        while not self.closed:
            request=self.data_requests.get()
            if request is None:return
            try:
                check=connect();empty=not check.execute('SELECT 1 FROM clips LIMIT 1').fetchone();check.close()
                if empty:
                    from core import inventory,decode_all
                    inventory(GAME);decode_all()
                name=request['name']
                if (request['recount'] or name not in self.conversion_cache) and name not in self.conversion_verifying:
                    self.conversion_verifying.add(name)
                    def verify(profile=name):
                        try:self.conversion_results.put((profile,converted_keys(profile),None))
                        except Exception as exc:self.conversion_results.put((profile,{},str(exc)))
                    threading.Thread(target=verify,daemon=True).start()
                converted=self.conversion_cache.get(name,{})
                if name!=cached_name or request['recount'] or cached_converted is not converted:
                    if request['name']!=cached_name:
                        # Show the editable rows before touching thousands of
                        # source files on a slow disk. Verify conversion next.
                        counts=dict(topics={},loading=True)
                        rows,total=paired_page(request['name'],category=request['category'],offset=request['offset'],state=request['state'],converted=converted,original_query=request['original_query'],source_query=request['source_query'])
                        self.data_results.put((True,dict(request=request,rows=rows,total=total,converted=converted,counts=counts)))
                    counts=coverage(name,converted);cached_name=name;cached_converted=converted
                rows,total=paired_page(request['name'],category=request['category'],offset=request['offset'],state=request['state'],converted=converted,original_query=request['original_query'],source_query=request['source_query'])
                self.data_results.put((True,dict(request=request,rows=rows,total=total,converted=converted,counts=counts)))
            except Exception as exc:self.data_results.put((False,dict(request=request,error=str(exc))))

    def write_worker(self):
        import time
        while True:
            queries=self.write_requests.get()
            if queries is None:self.write_requests.task_done();return
            while True:
                db=None
                try:
                    db=connect()
                    for sql,values in queries:db.execute(sql,values)
                    db.commit();self.write_results.put((True,''));break
                except sqlite3.OperationalError as exc:
                    if db is not None:db.rollback()
                    self.write_results.put((False,str(exc)));time.sleep(.5)
                finally:
                    if db is not None:db.close()
            self.write_requests.task_done()

    def tree(self,parent,labels,widths,columns=('name','text'),row=2):
        frame=ttk.Frame(parent); frame.grid(row=row,column=0,sticky='nsew')
        tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse',height=5)
        for col,label,width in zip(columns,labels,widths):
            tree.heading(col,text=label); tree.column(col,width=width,minwidth=80)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=self.scroll_both)
        tree.configure(yscrollcommand=lambda first,last,t=tree:self.scrolled(t,first,last))
        tree.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y')
        self.scrolls[tree]=scroll
        tree.bind('<MouseWheel>',self.wheel)
        tree.bind('<KeyRelease>',lambda e,t=tree:self.sync_view(t))
        return tree

    def scroll_both(self,*args):
        for tree in (self.left,self.right): tree.yview(*args)

    def wheel(self,event):
        self.scroll_both('scroll',-int(event.delta/120),'units'); return 'break'

    def scrolled(self,tree,first,last):
        self.scrolls[tree].set(first,last)

    def sync_view(self,tree):
        other=self.right if tree==self.left else self.left
        other.yview_moveto(tree.yview()[0])

    def pause_other(self,player):
        for other in self.players:
            if other is not player: other.pause()

    def category(self):
        return self.topic_labels.get(self.topic_filter.get())

    def update_coverage(self,schedule=True):
        self.request_data(recount=True)

    def display_coverage(self):
        selected=self.category(); self.topic_labels={'Todos os assuntos':None}
        values=['Todos os assuntos']
        for label in TOPICS:
            count=self.counts['topics'].get(label,{}).get('total',0)
            display=label if self.counts.get('loading') else f'{label} · {number(count)}'; self.topic_labels[display]=label; values.append(display)
        self.topic_box['values']=values
        self.topic_filter.set(next((key for key,value in self.topic_labels.items() if value==selected),'Todos os assuntos'))
        self.show_counts()

    def periodic_coverage(self):
        if self.closed:return
        if self.data_loaded:self.request_data(recount=True)
        self.after(30000,self.periodic_coverage)

    def report_callback_exception(self,kind,error,trace):
        import traceback
        with (APP_ROOT/'studio_error.log').open('a',encoding='utf8') as log:
            log.write(''.join(traceback.format_exception(kind,error,trace)))
        self.status.set('Não foi possível concluir a ação: '+str(error))

    def show_counts(self):
        if self.counts.get('loading'):
            self.original_count.set('Carregando contagem de ocorrências…');self.custom_count.set('Verificando áudios e conversões…');return
        counts=self.counts['topics'].get(self.category(),self.counts)
        total,linked,ready,texts=(counts.get(k,0) for k in ('total','linked','converted','transcribed'))
        self.original_count.set(f'{number(total)} ocorrências · {number(texts)} transcritas\n{number(total-texts)} transcrições pendentes no original')
        if self.profile.get()=='Tiago Leifert':
            self.custom_count.set(f'{number(total)} falas originais disponíveis\nProjeto original: usa os áudios do jogo')
        else:
            if self.profile.get() not in self.conversion_cache:
                self.custom_count.set(f'{number(linked)} com áudio · verificando conversões…\n{number(total-linked)} sem áudio próprio')
            else:
                reviewed=counts.get('reviewed',0)
                pending_review=counts.get('pending_review',max(0,linked-reviewed))
                self.custom_count.set(f'{number(linked)} com áudio · {number(ready)} convertidas\n{number(total-ready)} não convertidas · {number(total-linked)} sem áudio próprio\n{number(reviewed)} aprovadas · {number(pending_review)} pendentes de revisão')

    def schedule_refresh(self):
        if self.refresh_job: self.after_cancel(self.refresh_job)
        self.refresh_job=self.after(350,self.refresh_original)

    def refresh_original(self):
        self.refresh_job=None; self.offset=0; self.load_original()

    def load_original(self):
        self.save_visible_texts()
        self.request_data()

    def display_data(self,data):
        request=data['request']
        if request['generation']!=self.data_generation:return
        self.save_visible_texts()
        previous=request['selected'];rows=data['rows'];self.total_rows=data['total']
        for row in rows:
            if row['wav'] in self.local_original_text:row['transcript']=self.local_original_text[row['wav']]
            if row['source_key'] in self.local_source_text:row['source_transcript']=self.local_source_text[row['source_key']]
            if request['name'] not in self.conversion_cache and request['name']!='Tiago Leifert' and row['source_key']:
                row['conversion']='Verificando conversão'
        self.counts=data['counts'];self.converted=data['converted'];self.display_coverage();self.data_loaded=True
        self.originals={row['key']:row for row in rows}
        self.loaded_profile=self.profile.get()
        self.sources={row['key']:dict(key=row['source_key'],path=row['source_path'],transcript=row['source_transcript'] or '',duration=row['source_duration'] or 0,event=row['source_event'] or '',topic=row['source_topic'] or row['topic'],confidence=row['source_confidence']) for row in rows if row['source_key']}
        self.current_key=None
        self.left.delete(*self.left.get_children()); self.right.delete(*self.right.get_children())
        for row in rows:
            self.left.insert('','end',iid=row['key'],values=(f"{row['topic']} · {row['row']}",row['transcript'] or '[Transcrição pendente]'))
            filename=Path(row['source_path']).name if row['source_path'] else '＋ Importar áudio nesta fala'
            uses=row.get('source_uses',0)
            reuse=(' · Usado '+str(uses)+' vezes' if uses>1 else ' · Uso único' if uses else '')
            reviewed=bool(row.get('reviewed')) and bool(row['source_key'])
            check='☑' if reviewed else '☐' if row['source_key'] and request['name']!='Tiago Leifert' else '—'
            tags=('approved',) if reviewed else ()
            self.right.insert('','end',iid=row['key'],values=(check,row['conversion']+reuse+' · '+filename,row['source_transcript'] or ('[Transcrição pendente]' if row['source_key'] else '[Ainda sem áudio próprio]')),tags=tags)
        self.progress.set(f'{number(self.offset+1 if rows else 0)}–{number(self.offset+len(rows))} de {number(self.total_rows)}')
        self.custom_title.configure(text='Sua narração · '+self.profile.get()); self.show_counts()
        if rows:
            key=previous if previous in self.originals else rows[0]['key']
            self.left.selection_set(key); self.select_row(self.left)
        else: self.display_selection(None)

    def page(self,delta):
        candidate=max(0,self.offset+delta)
        if candidate>=self.total_rows and candidate: return
        self.offset=candidate; self.load_original()

    def next_occurrence(self,direction):
        keys=list(self.left.get_children())
        if not keys:return
        index=keys.index(self.current_key) if self.current_key in keys else 0
        target=index+direction
        if 0<=target<len(keys):
            key=keys[target];self.left.selection_set(key);self.left.focus(key);self.left.see(key);self.select_row(self.left)
        else:self.page(direction*500)

    def review_cell_click(self,event):
        if self.right.identify_region(event.x,event.y)!='cell' or self.right.identify_column(event.x)!='#1':return
        key=self.right.identify_row(event.y)
        if not key or key not in self.originals:return 'break'
        self.right.selection_set(key);self.right.focus(key);self.select_row(self.right)
        row=self.originals[key];source=self.sources.get(key);name=self.profile.get()
        if source and name!='Tiago Leifert':
            self.save_visible_texts()
            reviewed=not bool(row.get('reviewed'))
            row['reviewed']=reviewed
            self.right.set(key,'reviewed','☑' if reviewed else '☐')
            self.right.item(key,tags=('approved',) if reviewed else ())
            if reviewed:
                sql='INSERT INTO narration_reviews(profile,clip,reviewed) VALUES (?,?,1) ON CONFLICT(profile,clip) DO UPDATE SET reviewed=1,updated_at=CURRENT_TIMESTAMP'
            else:sql='DELETE FROM narration_reviews WHERE profile=? AND clip=?'
            self.write_requests.put([(sql,(name,key))])
            self.schedule_autosave(name)
            self.status.set('Áudio aprovado e destacado em verde.' if reviewed else 'Aprovação removida.')
        return 'break'

    def repeat_variations(self):
        original=self.originals.get(self.current_key);source=self.sources.get(self.current_key);name=self.profile.get()
        if not original or not source or name=='Tiago Leifert':return
        window=tk.Toplevel(self);window.title('Repetir gravação nas variações');window.geometry('640x420');window.transient(self)
        ttk.Label(window,text='Use a mesma gravação em outras variações desta fala.',padding=14).pack(anchor='w')
        ttk.Label(window,text=source['transcript'] or Path(source['path']).name,wraplength=600,padding=(14,0)).pack(anchor='w')
        choices=tk.Listbox(window,selectmode='extended',exportselection=False);choices.pack(fill='both',expand=True,padx=14,pady=12)
        rows=[row for row in self.originals.values() if row['event']==original['event']]
        for row in rows:choices.insert('end',f"Variação {row['row']} · {row['transcript'][:90]}")
        def apply():
            selected=[rows[index]['key'] for index in choices.curselection()]
            if not selected:return
            window.destroy()
            def task():
                for key in selected:assign(name,key,source['key'],method='manual',score=1)
                projects.save(name);return f'Gravação aplicada a {len(selected)} referências selecionadas.'
            self.job(task)
        ttk.Button(window,text='Aplicar às variações selecionadas',command=apply).pack(fill='x',padx=14,pady=(0,14))

    def change_profile(self):
        self.save_visible_texts();self.request_data(recount=True)
        if self.library_panel:self.library_panel.refresh(reset=True)
        try:
            config=json.loads(CONFIG_PATH.read_text(encoding='utf8')) if CONFIG_PATH.is_file() else dict(CONFIG)
            config['last_profile']=self.profile.get()
            temporary=CONFIG_PATH.with_suffix('.tmp')
            temporary.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf8')
            temporary.replace(CONFIG_PATH)
        except OSError as exc:self.status.set('Não consegui salvar o último narrador escolhido: '+str(exc))

    def schedule_autosave(self,name=None):
        name=name or self.loaded_profile or self.profile.get()
        if not name or name=='Tiago Leifert':return
        self.autosave_requested=name
        if self.autosave_timer:
            try:self.after_cancel(self.autosave_timer)
            except tk.TclError:pass
        self.autosave_timer=self.after(900,self._start_autosave)

    def _start_autosave(self):
        self.autosave_timer=None
        if not self.autosave_requested:return
        if self.busy or self.autosave_running:
            self.autosave_timer=self.after(500,self._start_autosave);return
        name=self.autosave_requested;self.autosave_requested=None;self.autosave_running=True
        def save():
            try:
                self.write_requests.join()
                projects.save(name)
                self.autosave_results.put((name,None))
            except Exception as exc:self.autosave_results.put((name,str(exc)))
        threading.Thread(target=save,daemon=True).start()

    def show_library(self):
        if self.library_panel is None:
            from library_panel import LibraryPanel
            self.library_panel=LibraryPanel(self.pane,self)
        if str(self.library_panel) not in self.pane.panes():
            self.pane.add(self.library_panel,weight=1)
        if hasattr(self,'library_button'):self.library_button.configure(text='Ocultar assets')
        self.library_panel.refresh()

    def toggle_library(self):
        if self.library_panel and str(self.library_panel) in self.pane.panes():
            self.pane.forget(self.library_panel)
            if hasattr(self,'library_button'):self.library_button.configure(text='Mostrar assets')
        else:self.show_library()

    def refresh_sources(self):
        self.change_profile()

    def selected(self,tree,items):
        selection=tree.selection(); return items.get(selection[0]) if selection else None

    def select_row(self,tree):
        selected=tree.selection()
        if not selected or selected[0] not in self.originals: return
        key=selected[0]
        other=self.right if tree==self.left else self.left
        if other.selection()!=(key,): other.selection_set(key); other.focus(key)
        self.sync_view(tree)
        if key!=self.current_key: self.display_selection(key)

    def display_selection(self,key):
        if self.current_key and self.current_key!=key: self.save_visible_texts()
        self.current_key=key
        original=self.originals.get(key); source=self.sources.get(key)
        for widget,text in ((self.original_text,original['transcript'] if original else ''),(self.source_text,source['transcript'] if source else '')):
            widget.configure(state='normal')
            widget.delete('1.0','end'); widget.insert('1.0',text); widget.edit_modified(False)
        self.left_player.set_source(original['wav'] if original else None)
        self.right_player.set_source(source['path'] if source else None)
        self.source_text.configure(state='normal' if source else 'disabled')
        if original:
            self.reference.set(f"{original['topic']} · variante {original['row']} · referência {original['sound_id']:08x}")
            self.status.set(f"{original['event']} · original {original['duration']:.2f}s · {original['conversion']} · {original['bank']}")
        else: self.reference.set('Nenhuma ocorrência neste filtro.')

    def play_original(self): self.left_player.toggle()
    def play_source(self): self.right_player.toggle()

    def save_original(self):
        row=self.originals.get(self.current_key)
        if not row: return
        self.original_text.edit_modified(True);self.save_visible_texts();self.status.set('Salvando transcrição original…')

    def save_source(self):
        row=self.sources.get(self.current_key)
        if not row: return
        if self.profile.get()=='Tiago Leifert':
            self.original_text.delete('1.0','end'); self.original_text.insert('1.0',self.source_text.get('1.0','end').strip()); self.save_original(); return
        self.source_text.edit_modified(True);self.save_visible_texts()
        name=self.profile.get(); self.job(lambda:projects.save(name))

    def clear_link(self):
        row=self.originals.get(self.current_key)
        if not row or self.profile.get()=='Tiago Leifert': return
        name=self.profile.get();self.save_visible_texts()
        def task():
            db=connect()
            db.execute('DELETE FROM mappings WHERE profile=? AND clip IN (SELECT key FROM clips WHERE bank=? AND offset=?)',(name,row['bank'],row['offset']));db.commit();db.close()
            projects.save(name);return 'Esta fala voltou a usar o áudio original.'
        self.job(task)

    def import_audio(self):
        original=self.originals.get(self.current_key)
        if not original: messagebox.showinfo('Importar','Selecione a fala que deseja substituir.'); return
        name=self.profile.get()
        if name=='Tiago Leifert': messagebox.showinfo('Novo narrador','Clique em Novo narrador para criar sua versão com base no original.'); return
        paths=filedialog.askopenfilenames(title='Importar áudio para esta ocorrência',filetypes=[('Áudio','*.wav *.mp3 *.flac *.ogg *.m4a'),('Todos','*.*')])
        if not paths: return
        def task():
            folder=USER_AUDIO_ROOT/projects.safe_name(name)/'Áudios individuais'; folder.mkdir(parents=True,exist_ok=True)
            imported=[]
            for path in paths:
                source=Path(path).expanduser().resolve()
                try:source.relative_to(USER_AUDIO_ROOT.resolve());managed=True
                except ValueError:managed=False
                target=source if managed else folder/(hashlib.sha256(str(source).encode()).hexdigest()[:8]+'_'+source.name)
                if not managed:
                    shutil.copy2(source,target)
                    for sidecar in (Path(str(source)+'.txt'),source.with_suffix('.txt')):
                        if sidecar.is_file():
                            side_target=Path(str(target)+'.txt') if sidecar==Path(str(source)+'.txt') else target.with_suffix('.txt')
                            if not side_target.exists():shutil.copy2(sidecar,side_target)
                imported.append(str(target))
                import_sources(name,target)
            if len(imported)==1:
                db=connect(); row=db.execute('SELECT key FROM sources WHERE narrator=? AND path=?',(name,imported[0])).fetchone(); db.close()
                assign(name,original['key'],row['key']); result='Áudio importado e colocado nesta ocorrência. Você já pode ouvir sua narração.'
            else: result='Áudios importados. Use Escolher da biblioteca para colocá-los nas falas desejadas.'
            projects.save(name); return result
        self.job(task)

    def open_library(self):
        original=self.originals.get(self.current_key); name=self.profile.get()
        if not original: return
        if name=='Tiago Leifert': messagebox.showinfo('Novo narrador','Crie um novo narrador para importar ou escolher áudios.'); return
        window=tk.Toplevel(self); window.title('Escolher áudio · '+name); window.geometry('1000x600'); window.transient(self)
        search=tk.StringVar(); bar=ttk.Frame(window,padding=10); bar.pack(fill='x')
        ttk.Label(bar,text='Buscar na sua biblioteca:').pack(side='left'); ttk.Entry(bar,textvariable=search).pack(side='left',fill='x',expand=True,padx=8)
        body=ttk.Frame(window); body.pack(fill='both',expand=True,padx=10)
        tree=ttk.Treeview(body,columns=('file','text'),show='headings',selectmode='browse')
        tree.heading('file',text='Seu arquivo'); tree.heading('text',text='Sua transcrição'); tree.column('file',width=380); tree.column('text',width=570)
        scroll=ttk.Scrollbar(body,command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y')
        rows={}; offset=0; total=0; progress=tk.StringVar()
        def load():
            nonlocal total
            text='%'+search.get()+'%'; db=connect()
            where='narrator=? AND (fold(path) LIKE fold(?) OR fold(transcript) LIKE fold(?))'
            params=(name,text,text)
            total=db.execute('SELECT count(*) FROM sources WHERE '+where,params).fetchone()[0]
            found=db.execute('SELECT * FROM sources WHERE '+where+' ORDER BY event,path LIMIT 500 OFFSET ?',params+(offset,)).fetchall(); db.close()
            rows.clear(); rows.update({r['key']:dict(r) for r in found}); tree.delete(*tree.get_children())
            for r in found: tree.insert('','end',iid=r['key'],values=(Path(r['path']).name,r['transcript'] or '[Transcrição pendente]'))
            progress.set(f'{offset+1 if found else 0}–{offset+len(found)} de {number(total)}')
        def find():
            nonlocal offset
            offset=0; load()
        def page(delta):
            nonlocal offset
            new=max(0,offset+delta)
            if new<total or new==0: offset=new; load()
        ttk.Button(bar,text='Buscar',command=find).pack(side='left')
        player=AudioPlayer(window,'Ouvir áudio da biblioteca',WORK/'preview_cache',FFMPEG,self.pause_other,self.status.set)
        self.players.append(player)
        player.pack(fill='x',padx=10,pady=8)
        tree.bind('<<TreeviewSelect>>',lambda e:player.set_source((self.selected(tree,rows) or {}).get('path')))
        footer=ttk.Frame(window,padding=10); footer.pack(fill='x')
        ttk.Button(footer,text='← Anteriores',command=lambda:page(-500)).pack(side='left')
        ttk.Button(footer,text='Próximos →',command=lambda:page(500)).pack(side='left',padx=6)
        ttk.Label(footer,textvariable=progress).pack(side='left')
        def close():
            player.shutdown()
            if player in self.players: self.players.remove(player)
            window.destroy()
        def choose():
            row=self.selected(tree,rows)
            if not row: return
            assign(name,original['key'],row['key']); close(); self.job(lambda:projects.save(name))
        ttk.Button(footer,text='Usar na ocorrência selecionada',command=choose).pack(side='right')
        window.protocol('WM_DELETE_WINDOW',close); load()

    def new_profile(self):
        name=simpledialog.askstring('Novo narrador','Nome do narrador (base: Tiago Leifert / Caio Ribeiro):')
        if not name: return
        commentator=simpledialog.askstring('Comentarista','Nome do comentarista:') or ''
        try: projects.new(name,commentator)
        except ValueError as exc: messagebox.showerror('Projeto',str(exc)); return
        self.profile_box['values']=projects.names(); self.profile.set(name); self.change_profile(); self.edit_project()

    def save_project(self):
        self.save_visible_texts()
        name=self.profile.get(); self.job(lambda:projects.save(name))

    def build_project(self):
        self.save_visible_texts()
        name=self.profile.get(); self.job(lambda:projects.build(name))

    def save_visible_texts(self):
        if not self.original_text.edit_modified() and not self.source_text.edit_modified(): return
        original=self.originals.get(self.current_key); source=self.sources.get(self.current_key)
        queries=[]
        if original and self.original_text.edit_modified():
            text=self.original_text.get('1.0','end').strip()
            queries.append(('UPDATE clips SET transcript=? WHERE wav=?',(text,original['wav'])))
            self.local_original_text[original['wav']]=text
            for key,item in self.originals.items():
                if item['wav']==original['wav']:
                    item['transcript']=text
                    if self.left.exists(key): self.left.set(key,'text',text)
        if source and self.source_text.edit_modified():
            text=self.source_text.get('1.0','end').strip()
            if self.loaded_profile=='Tiago Leifert':
                queries.append(('UPDATE clips SET transcript=? WHERE wav=?',(text,source['path'])))
                self.local_original_text[source['path']]=text
            else:
                queries.append(('UPDATE sources SET transcript=?,confidence=0,topic=? WHERE key=?',(text,topic(source['event'],source['path'],text),source['key'])))
                self.local_source_text[source['key']]=text
            for key,item in self.sources.items():
                if item['key']==source['key']:
                    item['transcript']=text
                    if self.right.exists(key): self.right.set(key,'text',text)
        if queries:
            self.write_requests.put(queries)
            self.schedule_autosave(self.loaded_profile)
        self.original_text.edit_modified(False); self.source_text.edit_modified(False)

    def open_project(self):
        path=filedialog.askdirectory(title='Importe um projeto ou selecione Narrations\\<narrador>',initialdir=str(GAME/'Narrations'))
        if path: self.job(lambda:dict(opened=projects.open_project(path)))

    def edit_project(self):
        name=self.profile.get(); data=projects.metadata(name); window=tk.Toplevel(self); window.title('Projeto · '+name); window.geometry('640x580'); window.transient(self)
        commentator=tk.StringVar(value=data.get('commentator','')); new_name=tk.StringVar(value=name)
        ttk.Label(window,text=name,font=('Segoe UI',18,'bold')).pack(anchor='w',padx=18,pady=14)
        ttk.Label(window,text='Nome do narrador (alterar cria uma cópia do projeto)').pack(anchor='w',padx=18); ttk.Entry(window,textvariable=new_name).pack(fill='x',padx=18,pady=6)
        ttk.Label(window,text='Comentarista').pack(anchor='w',padx=18); ttk.Entry(window,textvariable=commentator).pack(fill='x',padx=18,pady=6)
        ttk.Label(window,text='Competições no modo carreira (sem seleção = escolha manual)').pack(anchor='w',padx=18,pady=6)
        available=competitions(GAME); choices=tk.Listbox(window,selectmode='extended',exportselection=False,height=14); choices.pack(fill='both',expand=True,padx=18)
        for i,item in enumerate(available):
            choices.insert('end',item['name']+' · ID '+item['id'])
            if item['id'] in data.get('competitions',[]): choices.selection_set(i)
        portrait=tk.StringVar(value=data.get('portrait',''))
        def pick_photo():
            path=filedialog.askopenfilename(filetypes=[('Imagem','*.png *.jpg *.jpeg *.webp')])
            if not path: return
            from PIL import Image
            dest=projects.folder(name); dest.mkdir(parents=True,exist_ok=True)
            image=Image.open(path); image.thumbnail((128,128)); image.convert('RGBA').save(dest/'portrait.png'); portrait.set('portrait.png')
        ttk.Button(window,text='Escolher imagem do narrador',command=pick_photo).pack(anchor='w',padx=18,pady=8)
        ttk.Label(window,textvariable=portrait).pack(anchor='w',padx=18)
        def commit():
            try:
                target=projects.safe_name(new_name.get())
                if target!=name:
                    projects.clone(name,target)
                    if portrait.get() and (projects.folder(name)/portrait.get()).is_file(): shutil.copy2(projects.folder(name)/portrait.get(),projects.folder(target)/'portrait.png')
                projects.save(target,commentator.get(),[available[i]['id'] for i in choices.curselection()],portrait.get())
                self.profile_box['values']=projects.names(); self.profile.set(target); window.destroy(); self.change_profile(); self.status.set('Configuração salva. Converta e instale para aplicar no jogo.')
            except ValueError as exc: messagebox.showerror('Projeto',str(exc),parent=window)
        ttk.Button(window,text='Salvar configuração do projeto',command=commit).pack(fill='x',padx=18,pady=14)

    def transcribe_selected(self,original=False):
        row=self.originals.get(self.current_key) if original else self.sources.get(self.current_key)
        if not row: messagebox.showinfo('Transcrição','Importe ou escolha o áudio desta ocorrência primeiro.'); return
        table='clips' if original or self.profile.get()=='Tiago Leifert' else 'sources'
        name=self.profile.get(); key=row['key']; self.job(lambda:self.run_worker(['--table',table,'--key',key,'--project',name]))

    def run_worker(self,args):
        worker=RESOURCE_ROOT/'AI/TranscriptionWorker.exe'
        if not worker.exists():worker=APP_ROOT/'AI/TranscriptionWorker.exe'
        command=[str(worker)] if worker.exists() else [str(CODE_ROOT/'.venv/Scripts/python.exe'),str(CODE_ROOT/'transcription_worker.py')]
        env=dict(__import__('os').environ)
        config=WORK/'worker_config.json';config.parent.mkdir(parents=True,exist_ok=True)
        config.write_text(json.dumps(dict(game=str(GAME),catalog_root=str(WORK),projects=str(PROJECTS),source_root=str(SOURCE_ROOT),whisper_model=str(WHISPER_MODEL)),ensure_ascii=False),encoding='utf8')
        env['F16_NARRATION_CONFIG']=str(config)
        result=subprocess.run(command+args,capture_output=True,env=env,creationflags=0x08000000)
        if result.returncode: raise ValueError(result.stderr.decode('utf8',errors='replace')[-1200:])
        return 'Transcrição deste áudio salva no projeto.'

    def job(self,fn,refresh=True):
        if self.busy: messagebox.showinfo('Processando','Aguarde a tarefa em andamento.'); return
        self.busy=True; self.status.set('Processando…'); self._refresh_after_job=refresh
        def task():
            try:
                self.write_requests.join()
                self.queue.put((True,fn() or 'Projeto salvo.'))
            except Exception as exc: self.queue.put((False,str(exc)))
        threading.Thread(target=task,daemon=True).start()

    def poll(self):
        if self.closed:return
        try:
            while True:
                name,converted,error=self.conversion_results.get_nowait()
                self.conversion_verifying.discard(name)
                if error:self.status.set('Não foi possível verificar conversões: '+error)
                else:
                    self.conversion_cache[name]=converted
                    if name==self.profile.get():self.request_data(recount=False)
        except queue.Empty:pass
        try:
            while True:
                ok,data=self.data_results.get_nowait()
                if data['request']['generation']!=self.data_generation:continue
                if ok:self.display_data(data)
                else:self.status.set('Não foi possível carregar o catálogo: '+data['error'])
        except queue.Empty:pass
        try:
            while True:
                ok,error=self.write_results.get_nowait()
                if not ok:self.status.set('Salvando quando o catálogo ficar disponível… '+error)
        except queue.Empty:pass
        try:
            while True:
                name,error=self.autosave_results.get_nowait();self.autosave_running=False
                if error:self.status.set('Falha no salvamento automático: '+error)
                elif name==self.profile.get():self.status.set(f'Edição salva automaticamente em Narrations\\{name}\\Studio. Use “Gerar áudio e instalar no jogo” para atualizar a voz da partida.')
                if self.autosave_requested and not self.autosave_timer:self.autosave_timer=self.after(300,self._start_autosave)
        except queue.Empty:pass
        try:
            ok,result=self.queue.get_nowait(); self.busy=False
            if isinstance(result,dict) and 'opened' in result:
                self.profile_box['values']=projects.names(); self.profile.set(result['opened']); result='Projeto aberto: '+result['opened']
            if self._refresh_after_job:
                self.update_coverage(schedule=False); self.load_original()
                if self.library_panel:self.library_panel.refresh()
            self.status.set(str(result))
            if not ok: messagebox.showerror('Tarefa não concluída',result)
        except queue.Empty: pass
        self.after(100,self.poll)

    def close_app(self):
        if self.busy: messagebox.showinfo('Processando','Aguarde a tarefa terminar antes de fechar.'); return
        self.save_visible_texts()
        if self.autosave_timer:
            try:self.after_cancel(self.autosave_timer)
            except tk.TclError:pass
            self.autosave_timer=None
        if self.autosave_requested and not self.autosave_running:self._start_autosave()
        if self.autosave_running or self.autosave_requested:
            self.status.set('Salvando a edição em Narrations antes de fechar…');self.after(100,self.close_app);return
        if self.write_requests.unfinished_tasks:
            self.status.set('Salvando suas últimas alterações antes de fechar…');self.after(100,self.close_app);return
        self.closed=True
        self.write_requests.put(None)
        try:self.data_requests.get_nowait()
        except queue.Empty:pass
        self.data_requests.put_nowait(None)
        for player in self.players: player.shutdown()
        self.destroy()


if __name__=='__main__':
    import sys
    try:
        if '--smoke' in sys.argv:
            app=Studio()
            startup_checkpoint('smoke-verifying')
            import time
            app.withdraw();deadline=time.monotonic()+60
            while (not app.data_loaded or app.counts.get('loading')) and time.monotonic()<deadline:
                app.update();time.sleep(.01)
            if not app.data_loaded or app.counts.get('loading'):raise ValueError('Catálogo ou contagem não ficaram disponíveis no teste de abertura.')
            report=dict(projects=projects.names(),catalog=str(DB),original_rows=len(app.originals),paired_rows=list(app.left.get_children())==list(app.right.get_children()),review_column='reviewed' in app.right['columns'],independent_searches=hasattr(app,'original_search') and hasattr(app,'source_search'),counts=app.counts,status='ok')
            (APP_ROOT/'studio_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8'); app.close_app(); startup_checkpoint('smoke-complete')
        else:
            default=CONFIG.get('last_profile','Vilani')
            profile,create_new=choose_profile(projects.names(),GAME,DB,default)
            if profile is None and not create_new:raise SystemExit(0)
            app=Studio(profile or 'Tiago Leifert')
            if create_new:app.after(250,app.new_profile)
            app.mainloop()
    except Exception:
        import traceback
        (APP_ROOT/'studio_error.log').write_text(traceback.format_exc(),encoding='utf8')
        if '--smoke' not in sys.argv: raise
