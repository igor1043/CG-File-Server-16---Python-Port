"""Prepare native assets off the UI thread; publish only between fixtures."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil,time
from .file_tools import _files_match,stadium_injection_paths
from .stadium_transaction import StadiumAssetTransaction


def idle_asset_page(app):
    page=(getattr(app,'lastpagename','') or '').lower()
    if getattr(app,'_closing',False) or getattr(app,'_stadium_task_running',False):return False
    if page=='game/screens/playnow/kickoffhub':return not getattr(app,'_stadium_fixture_entered',False)
    return bool(getattr(app,'_match_audio_ended',False) and
                page.endswith(('/fluxhub','/sideselect','/selectteam')))


def prepare_restore(app):
    """Stage only changed files, once per path, without touching live assets."""
    game=Path(app.exedir);fsw=game/'FSW';files={};managed=set()
    for src,dst in ((fsw/'stadium',Path('data/sceneassets')),
                    (fsw/'TVLogo',Path('data/ui/game/overlays')),
                    (fsw/'ScoreBoard',Path('data/ui/game')),
                    (getattr(app,'Psource',fsw/'Police'),Path('data/sceneassets/slc')),
                    (getattr(app,'Nsource',fsw/'Nets'),Path('data/sceneassets/goalnet')),
                    (getattr(app,'PitchMowsource',fsw/'PitchMowPattern'),Path('data/sceneassets/pitch')),
                    (fsw/'bcdata/camera',Path('data/bcdata/camera'))):
        src=Path(src)
        if src.is_dir():
            for item in src.rglob('*'):
                if item.is_file() and item.suffix.lower()!='.png':files[dst/item.relative_to(src)]=item
    for slot in ('176','261'):
        for item in stadium_injection_paths(slot):
            rel=Path('data/sceneassets')/item;source=fsw/'Stadium'/item
            if source.is_file():files[rel]=source
            elif (game/rel).is_file():managed.add(rel)
        camera=Path('data/bcdata/camera')/f'bcstadiumcams_{slot}.dat'
        if camera not in files and (game/camera).is_file():managed.add(camera)
    transaction=StadiumAssetTransaction(game,app.log)
    try:
        for relative,source in files.items():
            if not _files_match(source,game/relative):
                target=transaction.stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
        # Invalidating routes is committed with the native loose files. Never
        # unlink content-addressed model/texture resources while FIFA is alive.
        for slot in (176,261):
            rel=Path(f'data/fifarna/lua/assets/server16_match_{slot}.lua')
            if (game/rel).is_file():
                target=transaction.stage/rel;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text(f'Server16MatchRoutes = Server16MatchRoutes or {{}}\nServer16MatchRoutes[{slot}] = nil\n',encoding='ascii')
        return transaction,managed
    except BaseException:
        transaction.accept();raise


class NativeAssetCleanup:
    def __init__(self,app):
        self.app=app;self.pending=False;self.future=None;self.retry_at=0
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='native-assets')

    def request(self):
        if not self.pending:self.app.log('Native asset restoration queued until the fixture has left results/replays')
        self.pending=True

    def _validate(self,scope):
        if not idle_asset_page(self.app) or scope!=getattr(self.app,'_kickoff_generation',0):
            raise RuntimeError('Fixture changed before native asset restoration; publication deferred')

    def pulse(self):
        if self.future is not None and self.future.done():
            future,self.future=self.future,None;transaction=None
            try:
                transaction,managed=future.result();self._validate(self.scope)
                transaction.commit(managed,lambda:self._validate(self.scope))
                changed=len(transaction.changes);self.pending=False
                self.app._stadium_assets_native=True
                self.app.log(f'Native assets restored between fixtures: {changed} changed paths; copies prepared in background')
            except Exception as error:
                self.retry_at=time.monotonic()+1;self.app.log('Native asset restoration deferred',error)
            finally:
                if transaction is not None:self.executor.submit(transaction.accept)
            return not self.pending
        if self.pending and self.future is None and time.monotonic()>=self.retry_at and idle_asset_page(self.app):
            self.scope=getattr(self.app,'_kickoff_generation',0)
            self.future=self.executor.submit(prepare_restore,self.app)
        return False

    def close(self):
        self.executor.shutdown(wait=True,cancel_futures=False)
        if self.future is not None:
            try:self.future.result()[0].accept()
            except Exception:pass
        self.pending=False;self.future=None
