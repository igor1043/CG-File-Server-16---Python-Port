"""Non-modal career notices using the retirement mod's visual/audio contract."""
from __future__ import annotations
import ctypes
from ctypes import wintypes

NOTICE_DURATION_MS = 5000


def native_notice(pid, text, persistent=False, dismiss=False):
    if not pid:
        return False
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.FindWindowExW.argtypes=[wintypes.HWND,wintypes.HWND,wintypes.LPCWSTR,wintypes.LPCWSTR]
    user.FindWindowExW.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.SendMessageTimeoutW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,
                                     wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype=wintypes.LPARAM
    class CopyData(ctypes.Structure):
        _fields_=[('dwData',ctypes.c_size_t),('cbData',wintypes.DWORD),('lpData',ctypes.c_void_p)]
    window=None
    while True:
        window=user.FindWindowExW(None,window,'FifaRetirementFeedbackWindow',None)
        if not window:return False
        owner=wintypes.DWORD()
        user.GetWindowThreadProcessId(window,ctypes.byref(owner))
        if owner.value==pid:break
    payload=ctypes.create_string_buffer(text.encode('cp1252',errors='replace'))
    packet=CopyData(0x16403 if dismiss else 0x16402 if persistent else 0x16401,
                    len(payload),ctypes.cast(payload,ctypes.c_void_p))
    result=ctypes.c_size_t()
    sent=user.SendMessageTimeoutW(window,0x4a,0,ctypes.addressof(packet),
                                  0x3,500,ctypes.byref(result))
    return bool(sent and result.value==1)


def play_sound(stage):
    import winsound
    winsound.MessageBeep(winsound.MB_ICONHAND if stage=='error' else winsound.MB_ICONASTERISK)


class CareerFeedback:
    def __init__(self, app):
        self.app=app
        self.seen=set()
        self.window=None
        self.hide_job=None
        self._progress=None
        self._native_active=False
        self._native_pid=0

    def show(self, stage, text, token, persistent=False):
        key=(token,stage,persistent)
        if key in self.seen:return
        self.seen.add(key)
        if len(self.seen)>128:self.seen={key}
        self._progress=(token,text) if persistent else None
        try:
            pid=getattr(self.app.memory,'process_id',0)
            self._native_active=native_notice(pid,text,persistent=persistent)
            self._native_pid=pid if self._native_active else 0
            if self._native_active:
                self._cancel_hide()
                if self.window is not None:self.window.withdraw()
            else:self._fallback(text,persistent=persistent)
        except Exception as exc:
            self.app.log('Career visual feedback failed',exc)
        if stage in ('prepared','done','error','cancelled','waiting_exit'):
            try:play_sound(stage)
            except Exception as exc:self.app.log('Career audio feedback failed',exc)
        self.app.log('Career feedback '+stage+': '+text.replace('\n',' | '))

    def _cancel_hide(self):
        if self.hide_job is not None:
            self.app.after_cancel(self.hide_job)
            self.hide_job=None

    def _schedule_hide(self, persistent):
        self._cancel_hide()
        if not persistent:self.hide_job=self.app.after(NOTICE_DURATION_MS,self.window.withdraw)

    def tick(self):
        if self._progress and self._native_active and not self.app.memory.is_open():
            # Continue the same progress notice if FIFA closes during preparation.
            self._native_active=False
            self._fallback(self._progress[1],persistent=True)

    def close(self):
        if self._progress and self._native_pid:
            try:native_notice(self._native_pid,'',dismiss=True)
            except Exception:pass
        self._progress=None
        self._cancel_hide()
        if self.window is not None:self.window.withdraw()

    def _fallback(self, text, persistent=False):
        # The native game window is preferred. This also delivers completion
        # when the player has closed FIFA while the Server remains open.
        if not hasattr(self.app,'tk'):return
        import tkinter as tk
        if self.window is None or not self.window.winfo_exists():
            self.window=tk.Toplevel(self.app)
            self.window.withdraw();self.window.overrideredirect(True)
            self.window.attributes('-topmost',True)
            self.window.configure(bg='#dbe3ed',padx=1,pady=1)
            card=tk.Frame(self.window,bg='white',padx=24,pady=14)
            card.pack(fill='both',expand=True)
            header=tk.Frame(card,bg='white')
            header.pack(fill='x',pady=(0,10))
            badge=tk.Canvas(header,width=28,height=28,bg='white',highlightthickness=0)
            badge.create_oval(0,0,27,27,fill='#e7effc',outline='')
            badge.create_text(14,13,text='i',fill='#0968f8',font=('Segoe UI',12,'bold'))
            badge.pack(side='left',padx=(0,10))
            tk.Label(header,text='FIFA FRIENDS  |  CARREIRA',bg='white',fg='#0968f8',
                     font=('Segoe UI',9,'bold')).pack(side='left')
            tk.Frame(card,bg='#e7edf5',height=1).pack(fill='x')
            self.label=tk.Label(card,bg='white',fg='#344651',font=('Segoe UI',13),
                                justify='left',anchor='w',wraplength=724)
            self.label.pack(fill='x',pady=(10,0))
        self.label.configure(text=text)
        self.window.update_idletasks()
        width,height=780,max(176,self.window.winfo_reqheight())
        self.window.geometry(f'{width}x{height}+{max(0,(self.app.winfo_screenwidth()-width)//2)}+42')
        # Show this app-owned notification without taking keyboard/controller focus.
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];user.GetAncestor.restype=wintypes.HWND
        user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
        hwnd=user.GetAncestor(self.window.winfo_id(),2)
        gdi=ctypes.WinDLL('gdi32',use_last_error=True)
        gdi.CreateRoundRectRgn.argtypes=[ctypes.c_int]*6
        gdi.CreateRoundRectRgn.restype=wintypes.HANDLE
        gdi.DeleteObject.argtypes=[wintypes.HANDLE]
        user.SetWindowRgn.argtypes=[wintypes.HWND,wintypes.HANDLE,wintypes.BOOL]
        region=gdi.CreateRoundRectRgn(0,0,width,height,20,20)
        if region and not user.SetWindowRgn(hwnd,region,False):gdi.DeleteObject(region)
        user.ShowWindow(hwnd,4)
        self._schedule_hide(persistent)
