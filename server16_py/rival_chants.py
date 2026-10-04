from __future__ import annotations

from pathlib import Path


class RivalChants:
    """Optional Support pool; playback and match lifecycle remain in ChantsRuntime."""

    CHANCE = 0.25

    def __init__(self, app):
        self.app = app
        self.context = None
        self.cache = {}
        self.failed = set()

    def _sync(self):
        context = (getattr(self.app, '_kickoff_generation', 0),
                   getattr(self.app, 'HID', ''), getattr(self.app, 'AID', ''),
                   str(getattr(self.app, 'exedir', '')))
        if context != self.context:
            self.context = context
            self.cache.clear()
            self.failed.clear()

    def tracks(self, support: Path, opponent) -> tuple[Path, ...]:
        self._sync()
        tokens = str(opponent or '').split()
        team_id = tokens[0] if tokens else ''
        if not team_id.isascii() or not team_id.isdecimal():
            return ()
        folder = support / 'Rivals' / team_id
        try:
            stamp = folder.stat().st_mtime_ns
            cached = self.cache.get(folder)
            if cached is None or cached[0] != stamp:
                # Do not recurse: only this opponent's files belong to the pool.
                root = folder.resolve()
                if not root.is_relative_to(support.resolve()):
                    return ()
                tracks = tuple(sorted(p for p in folder.glob('*.mp3')
                    if p.is_file() and p.stat().st_size > 0
                    and not p.name.casefold().endswith('.original.mp3')
                    and p.resolve().parent == root))
                self.cache[folder] = (stamp, tracks)
            return tuple(p for p in self.cache[folder][1] if p not in self.failed)
        except OSError:
            return ()

    def pick(self, support, opponent, last_track=None):
        tracks = self.tracks(support, opponent)
        candidates = [p for p in tracks if p != last_track]
        if not candidates or self.app._chants_rng.random() >= self.CHANCE:
            return None
        return self.app._chants_rng.choice(candidates)

    def reject(self, track):
        self._sync()
        self.failed.add(track)
