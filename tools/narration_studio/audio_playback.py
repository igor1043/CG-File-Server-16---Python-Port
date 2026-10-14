"""Two independent preview players, using the audio device's real position."""
from pathlib import Path
import ctypes
import hashlib
import queue
import subprocess
import threading
import uuid
import wave
import shutil
import tempfile
import tkinter as tk
from tkinter import ttk


class MciAudio:
    def __init__(self, send=None):
        self.alias = 'n' + uuid.uuid4().hex[:7]
        self.opened = False
        self.length = 0
        self.preview_directory=None
        self._send = send
        if send is None:
            self.winmm = ctypes.WinDLL('winmm')
            self.winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
            self.winmm.mciGetErrorStringW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]

    def command(self, command):
        if self._send is not None:
            return self._send(command)
        result = ctypes.create_unicode_buffer(1024)
        error = self.winmm.mciSendStringW(command, result, len(result), None)
        if error:
            message = ctypes.create_unicode_buffer(512)
            self.winmm.mciGetErrorStringW(error, message, len(message))
            raise ValueError(message.value or f'Falha no áudio: {error}')
        return result.value

    def load(self, path):
        self.close()
        if '"' in str(path):
            raise ValueError('Caminho de áudio inválido.')
        playable=Path(path).resolve()
        if self._send is None:
            # The legacy waveaudio driver rejects some Unicode/long paths.
            # A byte-for-byte copy gives it a short local filename.
            self.preview_directory=tempfile.TemporaryDirectory(prefix='f16_')
            playable=Path(self.preview_directory.name)/'audio.wav'
            shutil.copy2(path,playable)
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.GetShortPathNameW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint]
            buffer=ctypes.create_unicode_buffer(32768)
            size=kernel.GetShortPathNameW(str(playable),buffer,len(buffer))
            if size and size<len(buffer):playable=Path(buffer.value)
        try:self.command(f'open "{playable}" type waveaudio alias {self.alias}')
        except Exception:
            if self.preview_directory:self.preview_directory.cleanup();self.preview_directory=None
            raise
        self.opened = True
        try:
            self.command(f'set {self.alias} time format milliseconds')
            self.length = int(self.command(f'status {self.alias} length'))
        except Exception:
            self.close()
            raise

    @property
    def position(self):
        return int(self.command(f'status {self.alias} position')) if self.opened else 0

    @property
    def mode(self):
        return self.command(f'status {self.alias} mode') if self.opened else 'not ready'

    def play(self):
        if self.opened:
            position = self.position
            if position >= self.length:
                position = 0
            self.command(f'play {self.alias} from {position}')

    def pause(self):
        if self.opened and self.mode == 'playing':
            self.command(f'pause {self.alias}')

    def seek(self, milliseconds):
        if not self.opened:
            return
        was_playing = self.mode == 'playing'
        position = min(self.length, max(0, int(milliseconds)))
        self.command(f'stop {self.alias}')
        self.command(f'seek {self.alias} to {position}')
        if was_playing and position < self.length:
            self.command(f'play {self.alias} from {position}')

    def stop(self):
        if self.opened:
            self.command(f'stop {self.alias}')
            self.command(f'seek {self.alias} to start')

    def close(self):
        if self.opened:
            try:
                self.command(f'close {self.alias}')
            finally:
                self.opened = False
                self.length = 0
        if self.preview_directory:
            self.preview_directory.cleanup();self.preview_directory=None


def prepare_preview(source, cache, ffmpeg):
    path = Path(source)
    if not path.is_file():
        raise ValueError('Este áudio não está disponível. Importe uma gravação nesta ocorrência.')
    # Most original WAVs can be opened directly without blocking the interface.
    try:
        with wave.open(str(path)) as audio:
            if audio.getcomptype() == 'NONE' and audio.getsampwidth() == 2:
                return path
    except (wave.Error, EOFError):
        pass
    stat = path.stat()
    token = hashlib.sha256(f'{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (token + '.wav')
    if not target.exists():
        temporary = cache / (token + '.' + uuid.uuid4().hex + '.wav')
        try:
            result = subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(path),
                                     '-ac', '1', '-ar', '44100', '-c:a', 'pcm_s16le', str(temporary)],
                                    capture_output=True, timeout=120, creationflags=0x08000000)
            if result.returncode:
                raise ValueError(result.stderr.decode(errors='replace')[-800:])
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def clock_text(milliseconds):
    seconds = max(0, int(milliseconds)) / 1000
    return f'{int(seconds // 60):02d}:{seconds % 60:05.2f}'


class AudioPlayer(ttk.Frame):
    def __init__(self, parent, label, cache, ffmpeg, pause_other, report):
        super().__init__(parent, padding=(0, 3, 0, 3))
        self.audio = MciAudio()
        self.cache, self.ffmpeg = cache, ffmpeg
        self.pause_other, self.report = pause_other, report
        self.path = None
        self.generation = 0
        self.preparing = False
        self.closed = False
        self.dragging = False
        self.results = queue.Queue()
        self.value = tk.DoubleVar(value=0)
        self.time = tk.StringVar(value='00:00.00 / 00:00.00')
        self.caption = tk.StringVar(value='Selecione uma fala.')
        controls = ttk.Frame(self)
        controls.pack(fill='x')
        self.button = ttk.Button(controls, text='▶ ' + label, command=self.toggle, state='disabled')
        self.button.pack(side='left')
        self.label = label
        ttk.Button(controls, text='■ Parar', command=self.stop).pack(side='left', padx=6)
        ttk.Label(controls, textvariable=self.time).pack(side='right')
        self.scale = ttk.Scale(self, from_=0, to=1, variable=self.value, orient='horizontal')
        self.scale.pack(fill='x', pady=4)
        self.scale.bind('<ButtonPress-1>', lambda e: setattr(self, 'dragging', True))
        self.scale.bind('<ButtonRelease-1>', self.release_seek)
        self.scale.bind('<KeyRelease>', self.release_seek)
        ttk.Label(self, textvariable=self.caption, foreground='#68798c').pack(anchor='w')
        self.after(80, self.tick)

    def set_source(self, path):
        path = str(path) if path else None
        if path == self.path:
            return
        self.generation += 1
        self.preparing = False
        self.audio.close()
        self.path = path
        self.value.set(0)
        self.time.set('00:00.00 / 00:00.00')
        self.scale.configure(to=1)
        self.button.configure(text='▶ ' + self.label, state='normal' if path else 'disabled')
        name=Path(path).name if path else 'Sem áudio próprio. Use Importar áudio nesta ocorrência.'
        self.caption.set(name if len(name)<=60 else name[:57]+'…')

    def toggle(self):
        try:
            if not self.path or self.preparing:
                return
            if self.audio.opened:
                if self.audio.mode == 'playing':
                    self.audio.pause()
                else:
                    self.pause_other(self)
                    self.audio.play()
                return
            self.pause_other(self)
            self.preparing = True
            self.button.configure(text='Preparando áudio…', state='disabled')
            generation, source = self.generation, self.path
            def prepare():
                try:
                    self.results.put((generation, True, prepare_preview(source, self.cache, self.ffmpeg)))
                except Exception as exc:
                    self.results.put((generation, False, str(exc)))
            threading.Thread(target=prepare, daemon=True).start()
        except Exception as exc:
            self.report(str(exc))

    def pause(self):
        # Also cancel a queued request to play, while preserving its source.
        if self.preparing:
            self.generation += 1
            self.preparing = False
            self.button.configure(text='▶ ' + self.label, state='normal' if self.path else 'disabled')
        self.audio.pause()

    def stop(self):
        self.pause()
        self.audio.stop()
        self.value.set(0)

    def release_seek(self, event=None):
        self.dragging = False
        try:
            self.audio.seek(self.value.get())
        except Exception as exc:
            self.report(str(exc))

    def tick(self):
        if self.closed:
            return
        try:
            while True:
                generation, ok, result = self.results.get_nowait()
                if generation != self.generation:
                    continue
                self.preparing = False
                self.button.configure(text='▶ ' + self.label, state='normal' if self.path else 'disabled')
                if not ok:
                    self.report(result)
                    continue
                self.audio.load(result)
                self.scale.configure(to=max(1, self.audio.length))
                self.pause_other(self)
                self.audio.play()
        except queue.Empty:
            pass
        except Exception as exc:
            self.report(str(exc))
        try:
            if self.audio.opened:
                position, mode = self.audio.position, self.audio.mode
                if not self.dragging:
                    self.value.set(position)
                self.time.set(clock_text(position) + ' / ' + clock_text(self.audio.length))
                self.button.configure(text=('Ⅱ Pausar' if mode == 'playing' else '▶ ' + self.label))
        except Exception as exc:
            self.audio.close()
            self.report(str(exc))
        self.after(80, self.tick)

    def shutdown(self):
        self.closed = True
        self.generation += 1
        self.audio.close()
