from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


class StadiumAssetTransaction:
    """Publish prepared loose assets and retain backups until ID confirmation.

    FIFA's active injection slot must stay untouched. This is a reversible
    file transaction, not an atomic swap of the engine's in-memory assets.
    """

    def __init__(self, game: Path, logger) -> None:
        self.game = Path(game).resolve()
        runtime = self.game / 'runtime'
        runtime.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='server16_stadium_apply_', dir=runtime))
        self.stage = self.root / 'prepared'
        self.backup = self.root / 'previous'
        self.stage.mkdir()
        self.logger = logger
        self.changes: list[Path] = []
        self.closed = False

    def commit(self, managed: set[Path], validate) -> None:
        staged = {path.relative_to(self.stage) for path in self.stage.rglob('*') if path.is_file()}
        paths = staged | managed
        # Dependencies first; the model is published last. FIFA is switched
        # to this slot only after every file has been published successfully.
        paths = sorted(paths, key=lambda rel: (rel.name in ('stadium_176.rx3', 'stadium_261.rx3'), str(rel)))
        try:
            validate()
            for rel in paths:
                validate()
                if rel.is_absolute() or '..' in rel.parts:
                    raise RuntimeError(f'Invalid stadium destination: {rel}')
                dst = self.game / rel
                if not dst.resolve().is_relative_to(self.game):
                    raise RuntimeError(f'Stadium destination escapes game directory: {rel}')
                src, previous = self.stage / rel, self.backup / rel
                if dst.exists() and not dst.is_file():
                    raise RuntimeError(f'Stadium destination is not a file: {dst}')
                if dst.is_file():
                    previous.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(dst, previous)
                self.changes.append(rel)
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(src, dst)
            validate()
        except Exception:
            self.rollback()
            raise

    def rollback(self) -> None:
        if self.closed:
            return
        errors = []
        pending = []
        for rel in reversed(self.changes):
            dst, previous = self.game / rel, self.backup / rel
            try:
                if previous.is_file():
                    os.replace(previous, dst)
                else:
                    dst.unlink(missing_ok=True)
            except OSError as exc:
                errors.append(f'{rel}: {exc}')
                pending.append(rel)
        # A second recovery attempt must NOT unlink originals that the first
        # attempt already restored successfully (their backup was moved back).
        self.changes = list(reversed(pending))
        if errors:
            # Never discard the recovery copy when Windows refuses rollback.
            self.logger(f'Stadium rollback incomplete; recovery files: {self.backup}; {errors}')
            raise RuntimeError(f'Could not restore previous stadium assets; backups retained at {self.backup}')
        self.logger('Previous stadium assets restored after cancelled/failed application')
        self.accept()

    def accept(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            shutil.rmtree(self.root)
        except OSError as exc:
            self.logger(f'Stadium temporary files could not be removed: {self.root}', exc)
