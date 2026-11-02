"""Server16 audio settings tab for club substitution notifications."""
from pathlib import Path
import configparser
import tkinter as tk
from tkinter import ttk
from .substitution_audio import read_settings,save_settings


class SubstitutionAudioSettingsFrame(tk.Frame):
    def __init__(self,parent,app,spec):
        super().__init__(parent,bg=app.bg)
        self.app=app;self.path=Path(app.exedir)/'ModCarrerMode/config/substitution_audio.ini'
        self.pending=None;self.loading=True
        card=tk.Frame(self,bg=app.card);card.pack(fill='both',expand=True,padx=16,pady=16)
        tk.Label(card,text='Som de substituição',font=('Bahnschrift',20,'bold'),bg=app.card,fg=app.fg).pack(anchor='w',padx=24,pady=(24,8))
        tk.Label(card,text='Volume das notificações de substituição por clube.\nO áudio original do FIFA continua preservado.',justify='left',font=('Bahnschrift',11),bg=app.card,fg=app.muted).pack(anchor='w',padx=24,pady=(0,24))
        self.enabled=tk.BooleanVar(value=True)
        ttk.Checkbutton(card,text='Ativar sons de substituição',variable=self.enabled,command=self.schedule_save).pack(anchor='w',padx=24,pady=(0,24))
        self.volume=tk.DoubleVar(value=20);self.label=tk.StringVar(value='20%')
        bar=tk.Frame(card,bg=app.card);bar.pack(fill='x',padx=24)
        tk.Label(bar,text='Volume',font=('Bahnschrift',13,'bold'),bg=app.card,fg=app.fg).pack(side='left')
        tk.Label(bar,textvariable=self.label,font=('Bahnschrift',16,'bold'),bg=app.card,fg=app.gold).pack(side='right')
        self.slider=ttk.Scale(card,from_=0,to=100,variable=self.volume,command=self.schedule_save)
        self.slider.pack(fill='x',padx=24,pady=(12,4))
        tk.Label(card,text='0% · Silencioso                                      100% · Máximo',bg=app.card,fg=app.muted).pack(fill='x',padx=24)
        tk.Label(card,text='As alterações são salvas automaticamente e aplicadas sem reiniciar.\nO volume também muda durante um áudio que já estiver tocando.',justify='left',bg=app.card,fg=app.muted,font=('Bahnschrift',11)).pack(anchor='w',padx=24,pady=24)
        self.status=tk.StringVar()
        tk.Label(card,textvariable=self.status,justify='left',bg=app.card,fg=app.gold,font=('Bahnschrift',11)).pack(anchor='w',padx=24,pady=(0,12))
        tk.Label(card,text=str(self.path),bg=app.card,fg=app.muted,font=('Consolas',9),wraplength=900,justify='left').pack(anchor='w',padx=24,pady=(0,24))
        self.bind('<Destroy>',self._destroy);self.reload_entries()

    def reload_entries(self):
        if self.pending:return
        self.loading=True
        try:
            settings=read_settings(self.path);self.volume.set(round(settings.volume*100));self.enabled.set(settings.enabled)
            self.label.set(f'{round(settings.volume*100)}%');self.status.set('Configuração carregada.')
        except (OSError,ValueError,configparser.Error) as exc:self.status.set(f'Não foi possível ler: {exc}')
        finally:self.loading=False

    def schedule_save(self,*_):
        self.label.set(f'{round(self.volume.get())}%')
        if self.loading:return
        if self.pending:self.after_cancel(self.pending)
        self.pending=self.after(200,self.save)

    def save(self):
        self.pending=None
        try:
            settings=save_settings(self.path,volume=round(self.volume.get())/100,enabled=self.enabled.get())
            self.status.set(f'Aplicado · {round(settings.volume*100)}%' if settings.enabled else 'Sons de substituição desativados.')
        except (OSError,ValueError,configparser.Error) as exc:self.status.set(f'Não foi possível salvar: {exc}')

    def _destroy(self,event):
        if event.widget is not self:return
        if self.pending:
            self.after_cancel(self.pending);self.save()
