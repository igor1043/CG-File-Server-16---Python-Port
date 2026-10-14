"""Guided startup: validate the original catalogue, then choose a narrator."""
from pathlib import Path
import os
import sqlite3
import sys
import threading


def original_catalog_status(database):
    path=Path(database).resolve()
    if not path.is_file():
        raise FileNotFoundError('A base original do FIFA não foi encontrada: '+str(path))
    connection=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True,timeout=20)
    try:
        integrity=connection.execute('PRAGMA quick_check').fetchone()[0]
        if integrity!='ok':raise ValueError('O catálogo original precisa ser reparado: '+str(integrity))
        clips=connection.execute('SELECT count(*) FROM clips').fetchone()[0]
        recordings=connection.execute('SELECT count(DISTINCT wav) FROM clips WHERE wav IS NOT NULL AND wav!=""').fetchone()[0]
        if not clips:raise ValueError('A base original foi encontrada, mas não tem ocorrências para editar.')
        return {'clips':clips,'recordings':recordings}
    finally:connection.close()


def choose_profile(profile_names,game_root,database,default='Vilani'):
    """Show the packaged startup flow. Returns (profile_name, create_new)."""
    if '--smoke' in sys.argv or not getattr(sys,'frozen',False):
        return default,False

    import tkinter as tk
    from tkinter import ttk,messagebox

    result={'profile':None,'create':False,'closed':False}
    root=tk.Tk();root.title('Narration Studio · início');root.geometry('650x430');root.resizable(False,False)
    root.protocol('WM_DELETE_WINDOW',lambda:finish(None,False))
    outer=ttk.Frame(root,padding=26);outer.pack(fill='both',expand=True)
    ttk.Label(outer,text='FIFA 16 · Narration Studio',font=('Segoe UI',21,'bold')).pack(anchor='w')
    ttk.Label(outer,text='Localizando a base original e as narrações instaladas…',font=('Segoe UI',11)).pack(anchor='w',pady=(8,18))
    game_label=ttk.Label(outer,text='Jogo: '+str(game_root),wraplength=590,foreground='#53677c')
    game_label.pack(anchor='w',pady=(0,14))
    status=tk.StringVar(value='Abrindo a base original do Tiago Leifert e do Caio Ribeiro…')
    status_label=ttk.Label(outer,textvariable=status,wraplength=590,justify='left')
    status_label.pack(anchor='w',pady=(0,10))
    progress=ttk.Progressbar(outer,mode='indeterminate',length=590)
    progress.pack(fill='x',pady=(0,14));progress.start(12)
    choices=ttk.Frame(outer)
    selected=tk.StringVar(value=default if default in profile_names else (profile_names[0] if profile_names else 'Tiago Leifert'))
    ttk.Label(choices,text='Narrador ou projeto para abrir:').pack(anchor='w')
    selector=ttk.Combobox(choices,textvariable=selected,values=profile_names,state='readonly',width=58)
    selector.pack(fill='x',pady=(6,14))
    buttons=ttk.Frame(choices);buttons.pack(fill='x')

    def finish(profile,create):
        result['profile']=profile;result['create']=create;result['closed']=True
        try:progress.stop()
        except tk.TclError:pass
        root.destroy()

    def open_selected():finish(selected.get(),False)
    def create_new():finish(None,True)
    ttk.Button(buttons,text='Abrir narrador',command=open_selected).pack(side='right')
    ttk.Button(buttons,text='Criar novo narrador',command=create_new).pack(side='right',padx=8)
    ttk.Button(buttons,text='Fechar',command=lambda:finish(None,False)).pack(side='left')

    def loaded(summary,error,installed_count):
        if result['closed']:return
        progress.stop();progress.pack_forget()
        if error:
            status.set('Não consegui carregar a base original.\n'+error)
            messagebox.showerror('Falha ao abrir o catálogo',error,parent=root)
            choices.pack_forget()
            return
        status.set(
            f"Base original Tiago Leifert / Caio Ribeiro pronta: {summary['clips']:,} ocorrências "
            f"e {summary['recordings']:,} áudios de referência.\n"
            f"Perfis encontrados em Narrations no jogo: {installed_count}.".replace(',','.')
        )
        choices.pack(fill='x',pady=(10,0))
        if not installed_count:
            status.set(status.get()+'\nAinda não há perfis personalizados no jogo. Copie a pasta Narrations de “Coloque no FIFA 16” para a raiz do FIFA ou crie um novo narrador.')
        root.update_idletasks()

    def load():
        try:
            summary=original_catalog_status(database)
            narrator_root=Path(game_root)/'Narrations'
            installed_count=sum(1 for path in narrator_root.iterdir() if path.is_dir() and (path/'profile.npack').is_file()) if narrator_root.is_dir() else 0
            callback=lambda:loaded(summary,None,installed_count)
        except Exception as exc:
            error=str(exc);callback=lambda:loaded({},error,0)
        try:root.after(0,callback)
        except tk.TclError:pass

    threading.Thread(target=load,daemon=True).start()
    root.mainloop()
    return result['profile'],result['create']
