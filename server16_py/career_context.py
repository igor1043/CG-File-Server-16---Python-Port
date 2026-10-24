"""Read-only distinction between FIFA's shared FluxHub and a match pause.

FluxHub is used by the front end, career central and pause. Its page name
alone is insufficient. The competition engine is loaded for the active
competition session and releases its service registry when that session ends.
Never infer that FIFA exited from a failed read or module enumeration.
"""
from __future__ import annotations
import ctypes
import struct
import time
from .memory_access import (MODULEENTRY32W, TH32CS_SNAPMODULE,
                            TH32CS_SNAPMODULE32, INVALID_HANDLE_VALUE)


def _export(memory, base, size, wanted):
    """Resolve a named PE export by reading the target, without running it."""
    if memory.read_process_memory(base,2) != b'MZ':
        return None
    pe_offset = memory.read_uint32(base+0x3c)
    if not 0 < pe_offset < 4096:
        return None
    header = memory.read_process_memory(base+pe_offset,144)
    if header[:4] != b'PE\0\0' or struct.unpack_from('<H',header,24)[0] != 0x20b:
        return None
    rva, export_size = struct.unpack_from('<II',header,136)
    if not 0 < rva < size-40:
        return None
    directory = memory.read_process_memory(base+rva,40)
    functions, names, function_rva, name_rva, ord_rva = struct.unpack_from('<5I',directory,20)
    if not 0 < names <= functions <= 512:
        return None
    if any(not 0 < offset < size for offset in (function_rva,name_rva,ord_rva)):
        return None
    pointers = memory.read_process_memory(base+name_rva,names*4)
    for index in range(names):
        name = struct.unpack_from('<I',pointers,index*4)[0]
        if not 0 < name < size-128:
            continue
        if memory.read_process_memory(base+name,128).split(b'\0',1)[0] != wanted:
            continue
        ordinal = struct.unpack('<H',memory.read_process_memory(base+ord_rva+index*2,2))[0]
        if ordinal >= functions:
            return None
        target = memory.read_uint32(base+function_rva+ordinal*4)
        if not 0 < target < size-128 or rva <= target < rva+export_size:
            return None
        return base+target
    return None


def _career_service_active(memory, modules, details=False):
    # Verify the native accessor layouts before mirroring their READS. No
    # function in FIFA is called and no remote code or field is modified.
    context_getter = bytes.fromhex('4863411483f8ff750331c0c34869c01803000048034118c3')
    team_getter = bytes.fromhex('83fa0177114863c2486bc0744805a00100004801c8c3')
    game = memory.base_module
    if (memory.read_process_memory(game+0x5aafff0,len(context_getter)) != context_getter or
            memory.read_process_memory(game+0x5ac5940,len(team_getter)) != team_getter):
        return None
    descriptor = memory.read_process_memory(game+0x44575e0,24)
    if descriptor[7:9] != b'\xc7\x01':
        return None
    service_index = struct.unpack_from('<I',descriptor,9)[0]
    if not 0 <= service_index <= 4096:
        return None
    for base,size in modules:
        published = _export(memory,base,size,b'Fifa16CareerContextRead')
        if published is not None:
            record = memory.read_process_memory(published,48)
            schema,length,sequence,pid,service,expected,registry,epoch,_ = struct.unpack('<IIIIQQQII',record)
            if schema != 1 or length != 48 or sequence & 1 or pid != memory.process_id:
                return None
            if not service or not expected or not registry:
                return None
            wrapper = memory.read_int64(registry+service_index*32+24)
            if memory.read_int64(wrapper) != service or memory.read_int64(service) != expected:
                return None
            result = _selected_career_context(memory,service,registry,base,size,details)
            if isinstance(result,dict):result['context_epoch']=epoch
            if memory.read_process_memory(published,48) != record:
                return None
            return result
        entry = _export(memory,base,size,b'Fifa16CareerGetState')
        if entry is None:
            continue
        code = memory.read_process_memory(entry,96)
        marker = b'\x48\x8d\x54\x24\x50\x48\x8d\x4c\x24\x40\xe8'
        position = code.find(marker)
        if position < 0:
            continue
        call = entry+position+10
        live = call+5+struct.unpack_from('<i',code,position+11)[0]
        if not base <= live < base+size-64:
            continue
        body = memory.read_process_memory(live,64)
        a,b = body.find(b'\x48\x8b\x3d'),body.find(b'\x48\x8b\x35')
        if a < 0 or b < 0:
            continue
        owner_global = live+a+7+struct.unpack_from('<i',body,a+3)[0]
        vtable_global = live+b+7+struct.unpack_from('<i',body,b+3)[0]
        if not all(base <= addr < base+size-8 for addr in (owner_global,vtable_global)):
            continue
        owner,expected = memory.read_int64(owner_global),memory.read_int64(vtable_global)
        if not owner or not expected or memory.read_int64(owner) != expected:
            return None
        registry = memory.read_int64(owner+8)
        wrapper = memory.read_int64(registry+service_index*32+24)
        service = memory.read_int64(wrapper)
        return _selected_career_context(memory,service,registry,base,size,details)
    return None


def _selected_career_context(memory,service,registry,base,size,details):
    selected = struct.unpack('<i',memory.read_process_memory(service+0x14,4))[0]
    if selected == -1:return False
    if not 0 <= selected < 8:return None
    contexts = memory.read_int64(service+0x18)
    if not contexts:return None
    club = memory.read_uint32(contexts+selected*0x318+0x1a4)
    if not 0 < club <= 2_000_000:return False
    if details:
        protocol=_export(memory,base,size,b'Fifa16CareerJobOfferProtocol')
        return {'userid':selected,'club_id':club,
                'career_role':memory.read_uint32(contexts+selected*0x318+0x18c),
                'job_offer_protocol':memory.read_uint32(protocol) if protocol else 0,
                'registry_address':registry,'context_address':contexts+selected*0x318}
    return True


def competition_session(memory, details=False):
    kernel = getattr(memory, 'kernel32', None)
    pid = getattr(memory, 'process_id', 0)
    if kernel is None or not pid:
        return None
    snapshot = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32, pid)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        return None
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel.Module32FirstW(snapshot, ctypes.byref(entry))
        if not ok:
            return None
        modules,engine = [],None
        while ok:
            if entry.szModule.casefold() == 'footballcompengzf.dll':
                if entry.modBaseSize < 0xb13f8:
                    return None
                base = ctypes.addressof(entry.modBaseAddr.contents)
                if memory.read_process_memory(base,2) != b'MZ':
                    return None
                engine = memory.read_int64(base+0xb13f0)
            elif entry.szModule.casefold() == 'dinput8.dll':
                modules.append((ctypes.addressof(entry.modBaseAddr.contents),entry.modBaseSize))
            ok = kernel.Module32NextW(snapshot, ctypes.byref(entry))
        if not engine:
            return False
        # A loaded FootballCompEng DLL alone is not enough: tournaments share
        # it. Require a live native Career service and its active user club.
        return _career_service_active(memory,modules,details=details)
    except (OSError, RuntimeError, ValueError):
        return None
    finally:
        kernel.CloseHandle(snapshot)


class CareerContext:
    def __init__(self, app):
        self.app = app
        self.kind = None
        self.pid = 0
        self._next_probe = 0
        self._session = None
        self._profile = None

    def observe(self, page):
        pid = getattr(self.app.memory, 'process_id', 0)
        if pid != self.pid:
            self.pid, self.kind, self._next_probe = pid, None, 0
            self._profile = None
        page = (page or '').casefold()
        if '/career/' in page:
            self.kind = 'career'
        elif '/tournament/' in page or '/tournaments/' in page:
            self.kind = 'tournament'
        elif '/bootflow/' in page or '/mainmenu' in page or '/mainhub' in page:
            self.kind = None

    def started(self):
        try:
            offsets = self.app.offsets
            value = self.app.memory.get_int(offsets.GAMESTARTEDBINARYBASE, offsets.GAMESTARTEDBINARY)
            return value if type(value) is int and value in (0,1) else None
        except (AttributeError, OSError, RuntimeError, ValueError):
            return None

    def session(self, fresh=False):
        now = time.monotonic()
        if fresh or now >= self._next_probe:
            state = competition_session(self.app.memory, details=True)
            self._profile = state if isinstance(state, dict) else None
            self._session = True if self._profile else state
            self._next_probe = now+.25
        return self._session

    def profile(self, fresh=False):
        self.session(fresh=fresh)
        return self._profile

    def career_hub(self, page):
        self.observe(page)
        return ('/fluxhub/fluxhub' in (page or '').casefold()
                and self.started() == 0 and self.kind != 'tournament'
                and self.session() is True)

    def exited_hub(self, page, fresh=False):
        self.observe(page)
        return ('/fluxhub/fluxhub' in (page or '').casefold()
                and self.started() == 0 and self.session(fresh=fresh) is False)
