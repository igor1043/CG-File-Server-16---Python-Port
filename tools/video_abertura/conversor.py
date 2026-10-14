"""Conversor independente de abertura FIFA 16; Windows, Python 3.10+."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
FFMPEG = BASE / 'ffmpeg.exe'
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def seconds(value):
    h, m, s = value.split(':')
    return int(h)*3600 + int(m)*60 + float(s)


def command(source, output, bitrate='8M'):
    return [str(FFMPEG), '-hide_banner', '-nostdin', '-n', '-i', str(source),
            '-map', '0:v:0', '-map', '0:a:0?', '-map_metadata', '-1',
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,'
                   'pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=2997/100,format=yuv420p',
            '-c:v', 'libvpx', '-deadline', 'good', '-cpu-used', '2', '-threads', '8',
            '-crf', '10', '-b:v', bitrate, '-c:a', 'libvorbis', '-ar', '48000',
            '-ac', '2', '-progress', 'pipe:1', '-f', 'webm', str(output)]


def check_game_closed(destination):
    if not any((p/'fifa16.exe').exists() for p in (destination, *destination.parents)):
        return
    for name in ('fifa16.exe', 'Server16Python.exe'):
        result = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'],
                                capture_output=True, creationflags=HIDDEN, timeout=10)
        if result.returncode != 0:
            raise RuntimeError('Não foi possível verificar se o jogo está fechado. Escolha uma pasta fora do jogo.')
        if name.lower().encode() in result.stdout.lower():
            raise RuntimeError('Feche FIFA e Server16Python antes de substituir uma abertura na pasta do jogo.')


class WindowsDrop:
    """Native file drop: works on both the window and its child controls."""
    def __init__(self, root, events):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.shell = ctypes.WinDLL('shell32', use_last_error=True)
        pointer = ctypes.c_ssize_t
        self.callback_type = ctypes.WINFUNCTYPE(pointer, wintypes.HWND, wintypes.UINT,
                                                wintypes.WPARAM, wintypes.LPARAM)
        self.user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, pointer]
        self.user.SetWindowLongPtrW.restype = pointer
        self.user.CallWindowProcW.argtypes = [pointer, wintypes.HWND, wintypes.UINT,
                                             wintypes.WPARAM, wintypes.LPARAM]
        self.user.CallWindowProcW.restype = pointer
        self.shell.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
        self.shell.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                             wintypes.LPWSTR, wintypes.UINT]
        self.shell.DragQueryFileW.restype = wintypes.UINT
        self.shell.DragFinish.argtypes = [wintypes.HANDLE]
        self.user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetAncestor.restype = wintypes.HWND
        self.hooks = {}
        def receive(hwnd, msg, wp, lp):
            if msg == 0x233:  # WM_DROPFILES
                try:
                    count = self.shell.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                    paths = []
                    for i in range(count):
                        size = self.shell.DragQueryFileW(wp, i, None, 0)
                        buffer = ctypes.create_unicode_buffer(size+1)
                        self.shell.DragQueryFileW(wp, i, buffer, size+1)
                        paths.append(buffer.value)
                    events.put(('drop', paths))
                finally:
                    self.shell.DragFinish(wp)
                return 0
            return self.user.CallWindowProcW(self.hooks[hwnd], hwnd, msg, wp, lp)
        self.callback = self.callback_type(receive)
        root.update_idletasks()
        handles = {root.winfo_id(), self.user.GetAncestor(root.winfo_id(), 2)}
        def collect(widget):
            handles.add(widget.winfo_id())
            for child in widget.winfo_children(): collect(child)
        collect(root)
        for hwnd in handles:
            old = self.user.SetWindowLongPtrW(hwnd, -4, ctypes.cast(self.callback, ctypes.c_void_p).value)
            if old:
                self.hooks[hwnd] = old
                self.shell.DragAcceptFiles(hwnd, True)

    def close(self):
        for hwnd, old in self.hooks.items():
            self.shell.DragAcceptFiles(hwnd, False)
            self.user.SetWindowLongPtrW(hwnd, -4, old)
        self.hooks.clear()


class Converter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('FIFA Friends · Vídeo de abertura')
        self.geometry('760x710')
        self.minsize(720, 680)
        self.configure(bg='#f1f5fb')
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.busy = self.closing = False
        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self.bumper = tk.StringVar()
        self.bitrate = tk.StringVar(value='8 Mbps · perfil testado')
        self.status = tk.StringVar(value='Escolha um vídeo para começar.')
        self.percent = tk.StringVar(value='0%')
        self.log_lines = []
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#ffffff')
        style.configure('TLabel', background='#ffffff', foreground='#334155', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=(12, 9))
        style.configure('Blue.TButton', background='#1267ee', foreground='white')
        style.map('Blue.TButton', background=[('active', '#0953c7'), ('disabled', '#aac5eb')])
        style.configure('TEntry', padding=7)
        style.configure('TCombobox', padding=7)
        style.configure('Blue.Horizontal.TProgressbar', background='#1267ee', troughcolor='#e8eef8', borderwidth=0)
        card = ttk.Frame(self, padding=26)
        card.pack(fill='both', expand=True, padx=24, pady=24)
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text='Sua abertura, pronta para o FIFA 16', font=('Segoe UI', 20, 'bold')).grid(row=0, sticky='w')
        ttk.Label(card, text='Conversão em VP8 · Full HD · 29,97 FPS', foreground='#64748b').grid(row=1, sticky='w', pady=(5, 20))
        drop = tk.Label(card, text='↓\nArraste seu vídeo para esta janela\nou clique para escolher',
                        bg='#edf4ff', fg='#1267ee', font=('Segoe UI', 13), cursor='hand2', pady=17,
                        relief='solid', borderwidth=1)
        drop.grid(row=2, sticky='ew')
        drop.bind('<Button-1>', lambda _: self.choose_source())
        ttk.Label(card, text='Vídeo de origem').grid(row=3, sticky='w', pady=(17, 5))
        self.fields = []
        self.row(card, 4, self.source, 'Escolher vídeo', self.choose_source)
        ttk.Label(card, text='Pasta de destino · o arquivo será criado diretamente nela').grid(row=5, sticky='w', pady=(13, 5))
        self.row(card, 6, self.destination, 'Escolher pasta', self.choose_destination)
        options = ttk.Frame(card)
        options.grid(row=7, sticky='ew', pady=(14, 0))
        ttk.Label(options, text='Bitrate alvo').pack(side='left')
        self.combo = ttk.Combobox(options, textvariable=self.bitrate, state='readonly', width=28,
                                 values=['8 Mbps · perfil testado', '4 Mbps', '12 Mbps · experimental', '16 Mbps · experimental'])
        self.combo.pack(side='right')
        ttk.Label(card, text='bumper.big existente · opcional, para uma nova pasta de abertura').grid(row=8, sticky='w', pady=(14, 5))
        self.row(card, 9, self.bumper, 'Escolher bumper', self.choose_bumper)
        ttk.Label(card, text='Se o destino já tem bumper.big, basta converter o vídeo.\nO conversor não cria um bumper novo nem altera o jogo automaticamente.',
                  foreground='#64748b', font=('Segoe UI', 9)).grid(row=10, sticky='w', pady=(9, 15))
        progress = ttk.Frame(card)
        progress.grid(row=11, sticky='ew')
        ttk.Label(progress, textvariable=self.status, wraplength=590).pack(side='left')
        ttk.Label(progress, textvariable=self.percent, foreground='#1267ee').pack(side='right')
        self.bar = ttk.Progressbar(card, style='Blue.Horizontal.TProgressbar', maximum=100)
        self.bar.grid(row=12, sticky='ew', pady=(9, 15))
        actions = ttk.Frame(card)
        actions.grid(row=13, sticky='ew')
        self.open_button = ttk.Button(actions, text='Abrir destino', command=self.open_destination)
        self.open_button.pack(side='left')
        self.cancel_button = ttk.Button(actions, text='Cancelar', command=self.cancel, state='disabled')
        self.cancel_button.pack(side='right', padx=(8, 0))
        self.convert_button = ttk.Button(actions, text='Converter vídeo', style='Blue.TButton', command=self.start)
        self.convert_button.pack(side='right')
        self.drop = WindowsDrop(self, self.events)
        self.protocol('WM_DELETE_WINDOW', self.close)
        if len(sys.argv) > 1: self.set_source(sys.argv[1])
        self.after(100, self.poll)

    def row(self, parent, row, variable, label, callback):
        frame = ttk.Frame(parent)
        frame.grid(row=row, sticky='ew')
        frame.columnconfigure(0, weight=1)
        entry = ttk.Entry(frame, textvariable=variable)
        entry.grid(row=0, column=0, sticky='ew', padx=(0, 9))
        button = ttk.Button(frame, text=label, command=callback)
        button.grid(row=0, column=1)
        self.fields.extend([entry, button])

    def set_source(self, value):
        if self.busy: return
        path = Path(value)
        if path.is_file():
            self.source.set(str(path))
            self.status.set('Vídeo selecionado. Escolha a pasta e clique em Converter.')

    def choose_source(self):
        if not self.busy:
            value = filedialog.askopenfilename(title='Escolha o vídeo', filetypes=[('Vídeos', '*.mp4 *.mkv *.avi *.mov *.webm *.vp8'), ('Todos', '*.*')])
            if value: self.set_source(value)

    def choose_destination(self):
        value = filedialog.askdirectory(title='Pasta que receberá bootflowoutro.vp8')
        if value: self.destination.set(value)

    def choose_bumper(self):
        value = filedialog.askopenfilename(title='Escolha um bumper.big existente', filetypes=[('Bumper', '*.big')])
        if value: self.bumper.set(value)

    def open_destination(self):
        if Path(self.destination.get()).is_dir() and self.destination.get(): os.startfile(self.destination.get())

    def start(self):
        source, destination = Path(self.source.get()), Path(self.destination.get())
        if not self.source.get() or not source.is_file():
            messagebox.showerror('Vídeo ausente', 'Escolha um arquivo de vídeo válido.'); return
        if not self.destination.get() or not destination.is_dir():
            messagebox.showerror('Destino ausente', 'Escolha uma pasta de destino existente.'); return
        try: check_game_closed(destination)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            messagebox.showerror('Pasta do jogo em uso', str(exc)); return
        output = destination/'bootflowoutro.vp8'
        if source.resolve() == output.resolve():
            messagebox.showerror('Destino igual à origem', 'Escolha outra pasta para preservar o vídeo de origem.'); return
        if not FFMPEG.is_file():
            messagebox.showerror('Conversor ausente', 'ffmpeg.exe não foi encontrado junto ao fonte ou no EXE.'); return
        bumper = Path(self.bumper.get()) if self.bumper.get() else None
        if bumper and (not bumper.is_file() or bumper.name.lower() != 'bumper.big'):
            messagebox.showerror('Bumper inválido', 'Escolha um arquivo existente chamado bumper.big.'); return
        targets = [output] + ([destination/'bumper.big'] if bumper and bumper.resolve() != (destination/'bumper.big').resolve() else [])
        if any(p.exists() for p in targets) and not messagebox.askyesno('Substituir arquivos?', 'Já existem arquivos no destino. Substituir após converter?\nUma cópia dos arquivos anteriores será guardada na pasta backups-conversor.'):
            return
        self.busy = True
        self.cancel_event.clear()
        self.log_lines = []
        self.bar['value'] = 0
        self.percent.set('0%')
        self.status.set('Preparando conversão…')
        for widget in self.fields: widget.configure(state='disabled')
        self.combo.configure(state='disabled')
        self.convert_button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        bitrate = self.bitrate.get().split()[0]+'M'
        threading.Thread(target=self.convert, args=(source, destination, bumper, bitrate), daemon=True).start()

    def run(self, args, progress=False):
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace', creationflags=HIDDEN)
        duration = 0
        def cancel_watcher():
            while process.poll() is None:
                if self.cancel_event.wait(.15):
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired: process.kill()
                    except OSError: pass
                    return
        threading.Thread(target=cancel_watcher, daemon=True).start()
        for line in process.stdout:
            self.log_lines.append(line)
            match = re.search(r'Duration: (\d+:\d+:\d+\.\d+)', line)
            if match: duration = seconds(match[1])
            if progress and line.startswith('out_time=') and duration:
                try: value = min(89, seconds(line.strip().split('=', 1)[1])/duration*89)
                except ValueError: continue
                self.events.put(('progress', (value, 'Convertendo o vídeo…')))
        code = process.wait()
        process.stdout.close()
        if self.cancel_event.is_set(): raise InterruptedError('Conversão cancelada; arquivos anteriores preservados.')
        if code: raise RuntimeError('O FFmpeg não conseguiu concluir. Consulte o log de conversão.')

    def convert(self, source, destination, bumper, bitrate):
        stage = None
        changed = []
        backups = {}
        try:
            stage = Path(tempfile.mkdtemp(prefix='.conversor-', dir=destination))
            temp = stage/'bootflowoutro.vp8'
            self.run(command(source, temp, bitrate), True)
            self.events.put(('progress', (92, 'Validando vídeo e áudio…')))
            self.run([str(FFMPEG), '-v', 'error', '-nostdin', '-i', str(temp), '-f', 'null', 'NUL'])
            if temp.stat().st_size == 0: raise RuntimeError('Vídeo gerado vazio.')
            files = [(temp, destination/'bootflowoutro.vp8')]
            if bumper and bumper.resolve() != (destination/'bumper.big').resolve():
                shutil.copy2(bumper, stage/'bumper.big')
                files.append((stage/'bumper.big', destination/'bumper.big'))
            if self.cancel_event.is_set(): raise InterruptedError('Conversão cancelada.')
            check_game_closed(destination)
            backup = destination/'backups-conversor'/time.strftime('%Y%m%d_%H%M%S')
            for _, target in files:
                if target.exists():
                    backup.mkdir(parents=True, exist_ok=True)
                    previous = backup/target.name
                    shutil.copy2(target, previous)
                    backups[target] = previous
            for prepared, target in files:
                os.replace(prepared, target)
                changed.append(target)
            self.events.put(('done', str(destination/'bootflowoutro.vp8')))
        except Exception as exc:
            recovery_errors = []
            for target in reversed(changed):
                try:
                    if target in backups: shutil.copy2(backups[target], target)
                    else: target.unlink(missing_ok=True)
                except OSError as recovery:
                    recovery_errors.append(str(recovery))
            detail = str(exc)
            if recovery_errors: detail += '\nRestauração incompleta: '+ '; '.join(recovery_errors)
            self.events.put(('error', detail))
        finally:
            try: (destination/'conversao.log').write_text(''.join(self.log_lines), encoding='utf-8')
            except OSError: pass
            if stage is not None: shutil.rmtree(stage, ignore_errors=True)

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'drop':
                if len(value) != 1: messagebox.showinfo('Um vídeo por vez', 'Arraste apenas um vídeo para converter.')
                else: self.set_source(value[0])
            elif kind == 'progress':
                self.bar['value'] = value[0]
                self.percent.set(f'{value[0]:.0f}%')
                self.status.set(value[1])
            elif kind in ('done', 'error'):
                self.busy = False
                for widget in self.fields: widget.configure(state='normal')
                self.combo.configure(state='readonly')
                self.convert_button.configure(state='normal')
                self.cancel_button.configure(state='disabled')
                if self.closing:
                    self.drop.close(); self.destroy(); return
                if kind == 'done':
                    self.bar['value'] = 100; self.percent.set('100%')
                    self.status.set('Concluído! bootflowoutro.vp8 pronto para usar.')
                    messagebox.showinfo('Vídeo pronto', f'{value}\n\nConversão e decodificação verificadas.\nA reprodução ainda precisa ser conferida no FIFA.')
                else:
                    self.status.set(value)
                    messagebox.showerror('Conversão interrompida', value)
        self.after(100, self.poll)

    def cancel(self):
        self.cancel_event.set()
        self.status.set('Cancelando…')
        self.cancel_button.configure(state='disabled')

    def close(self):
        if self.busy:
            if messagebox.askyesno('Cancelar conversão?', 'Cancelar a conversão e fechar?'):
                self.closing = True; self.cancel()
        else:
            self.drop.close(); self.destroy()


if __name__ == '__main__':
    Converter().mainloop()
