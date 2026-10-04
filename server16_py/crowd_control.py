from __future__ import annotations

import ctypes
import mmap
import os

MAPPING_NAME = 'Local\\CGFS16_Crowd_v1'


class CrowdShared(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ('owner_pid', 'heartbeat', 'game_pid')]
    _fields_ += [(name, ctypes.c_int32) for name in (
        'generation', 'home_id', 'away_id', 'phase', 'requested_percent',
        'command', 'ack', 'status', 'current_percent', 'automatic_percent')]


class CrowdControl:
    """A volatile per-fixture request; never rewrites the career mod's INI."""

    def __init__(self, app):
        self.app = app
        self.context = None
        self.mapping = mmap.mmap(-1, ctypes.sizeof(CrowdShared), tagname=MAPPING_NAME)
        self.shared = CrowdShared.from_buffer(self.mapping)
        # The selector already checks that there is only one live server owner.
        self.shared.owner_pid = os.getpid()
        self.shared.phase = 0
        self.shared.requested_percent = -1
        self.shared.command += 1
        self.shared.status = 0
        self.shared.current_percent = self.shared.automatic_percent = -1

    @staticmethod
    def team_id(value):
        parts = str(value or '').split()
        try:
            number = int(parts[0]) if parts else 0
            return number if 0 < number < 2000000 else 0
        except ValueError:
            return 0

    def tick(self, prematch, playing):
        app, shared = self.app, self.shared
        context = (app._kickoff_generation, self.team_id(app.HID), self.team_id(app.AID))
        live = app.memory.is_open() and not getattr(app, '_closing', False)
        if context != self.context or not live or getattr(app, '_match_audio_ended', False):
            if context != self.context:
                shared.phase=0
                shared.requested_percent=-1
                shared.command=abs(shared.command)+1
                shared.status=1
                shared.current_percent=shared.automatic_percent=-1
            else:
                self.clear()
            self.context = context
        shared.generation, shared.home_id, shared.away_id = context
        shared.game_pid = app._resolve_fifa_pid() or 0 if live else 0
        shared.phase = (1 if prematch else 2 if playing else 0) if live and all(context[1:]) else 0
        if not shared.phase and shared.requested_percent >= 0:
            self.clear()
        shared.heartbeat = ctypes.windll.kernel32.GetTickCount()

    def clear(self):
        if self.shared.requested_percent != -1:
            command=abs(self.shared.command)+1
            self.shared.command=-command
            self.shared.requested_percent = -1
            self.shared.command = command

    def apply(self, value, context):
        normalized=(context[0],self.team_id(context[1]),self.team_id(context[2]))
        if (normalized != self.context or self.shared.phase != 1 or self.shared.status not in (2, 3)
                or self.shared.ack != self.shared.command):
            raise RuntimeError('Crowd bridge is not ready for this fixture')
        command=abs(self.shared.command)+1
        self.shared.command=-command
        self.shared.requested_percent = max(0, min(100, int(value)))
        self.shared.command = command
        return self.shared.command

    def shutdown(self):
        self.clear()
        self.shared.phase = self.shared.owner_pid = 0
        self.shared = None
        self.mapping.close()
