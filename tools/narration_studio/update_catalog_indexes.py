"""Explicit maintenance, separate from read-only GUI connection startup."""
from core import connect,DB,GAME
def run():
    for path in (DB,GAME/'Narrations/.studio/catalog.sqlite'):
        if not path.exists():continue
        db=connect(path)
        db.execute('CREATE INDEX IF NOT EXISTS clips_wav ON clips(wav)')
        db.execute('CREATE INDEX IF NOT EXISTS mappings_profile_source ON mappings(profile,source,clip)')
        db.execute('CREATE INDEX IF NOT EXISTS sources_narrator_path ON sources(narrator,path)')
        db.commit();db.close();print('Indexes ready:',str(path),flush=True)
if __name__=='__main__':run()
