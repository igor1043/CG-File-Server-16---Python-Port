"""Persistent pre-launch switch for the optional native cloth module."""
from pathlib import Path
import os
import re
import ctypes

MODULE = "cloth_motion/cloth_motion.dll"

def _atomic(path: Path, data: bytes) -> None:
    temporary=path.with_name(path.name+f".cloth-switch-{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()

def _section(text: str):
    start=re.search(r"(?mi)^\s*\[cloth_motion\][^\r\n]*(?:\r?\n|$)",text)
    if not start:return None
    end=re.search(r"(?m)^\s*\[",text[start.end():])
    return start.end(),start.end()+end.start() if end else len(text)

def _ini_enabled(data: bytes) -> bool:
    text=data.decode("utf-8-sig");section=_section(text)
    if not section:return False
    value=re.search(r"(?mi)^\s*enabled\s*=\s*([^;#\r\n]+)",text[section[0]:section[1]])
    return bool(value and value[1].strip()=="1")

def _ini_update(data: bytes, enabled: bool) -> bytes:
    bom=data.startswith(b"\xef\xbb\xbf");text=data.decode("utf-8-sig");section=_section(text)
    if not section:raise ValueError("A configuração da física de roupas não contém a seção cloth_motion.")
    newline="\r\n" if "\r\n" in text else "\n"
    body=text[section[0]:section[1]]
    pattern=r"(?mi)^([ \t]*enabled[ \t]*=[ \t]*)[^\r\n]*"
    if re.search(pattern,body):body=re.sub(pattern,lambda m:m[1]+("1" if enabled else "0"),body)
    else:body=f"enabled={int(enabled)}{newline}"+body
    result=(text[:section[0]]+body+text[section[1]:]).encode("utf-8")
    return (b"\xef\xbb\xbf" if bom else b"")+result

class ClothMotionSwitch:
    def __init__(self,game_directory):
        self.mods=Path(game_directory)/"ModCarrerMode"/"mods"
        self.list_path=self.mods/"enabled.txt"
        self.ini_path=self.mods/"cloth_motion"/"cloth_motion.ini"
        self.dll_path=self.mods/"cloth_motion"/"cloth_motion.dll"
        self.state_path=self.mods/"cloth_motion"/"runtime_state.txt"

    def available(self) -> bool:
        return self.dll_path.is_file() and self.ini_path.is_file() and self.list_path.is_file()

    def live_enabled(self, pid=None, now=None):
        """Confirmed native mode, or None for a missing/stale/other session."""
        try:
            fields=self.state_path.read_text(encoding='ascii').split()
            if len(fields)!=4 or fields[0]!='CM1':return None
            owner,stamp,value=map(int,fields[1:])
            if owner<=0 or value not in (0,1) or (pid is not None and owner!=pid):return None
            if now is None:
                clock=ctypes.windll.kernel32.GetTickCount64;clock.restype=ctypes.c_ulonglong
                now=clock()
            if not 0<=int(now)-stamp<=3000:return None
            return bool(value)
        except (OSError,ValueError,AttributeError,UnicodeError):return None

    def enabled(self) -> bool:
        try:
            present=any(row.strip().replace(b"\\",b"/").lower()==MODULE.encode() for row in self.list_path.read_bytes().splitlines())
            return present and self.dll_path.is_file() and _ini_enabled(self.ini_path.read_bytes())
        except (OSError,UnicodeError):return False

    def set_enabled(self,enabled: bool) -> None:
        # Keep unrelated modules byte-for-byte, including comments and order.
        before=self.list_path.read_bytes()
        if enabled and not self.dll_path.is_file():raise FileNotFoundError("O módulo de física de roupas não está instalado nesta pasta do FIFA.")
        ini_before=self.ini_path.read_bytes() if self.ini_path.exists() else None
        if enabled and ini_before is None:raise FileNotFoundError("A configuração da física de roupas não foi encontrada.")
        newline=b"\r\n" if b"\r\n" in before else b"\n"
        after=b"".join(row for row in before.splitlines(keepends=True) if row.strip().replace(b"\\",b"/").lower()!=MODULE.encode())
        # Keep the small native control bridge available when simulation is
        # off, so the user can turn physics back on during the same match.
        if self.dll_path.is_file() and ini_before is not None:
            after+=(b"" if not after or after.endswith(b"\n") else newline)+MODULE.replace("/","\\").encode()+newline
        ini_after=_ini_update(ini_before,enabled) if ini_before is not None else None
        changed=[]
        try:
            for path,old,new in [(self.ini_path,ini_before,ini_after),(self.list_path,before,after)]:
                if new is not None and new!=old:
                    _atomic(path,new);changed.append((path,old))
        except Exception:
            for path,old in reversed(changed):_atomic(path,old)
            raise
