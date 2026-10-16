import json,sqlite3,subprocess,ctypes,time
from pathlib import Path
from audio_playback import MciAudio,prepare_preview
from core import FFMPEG
db=sqlite3.connect(r'U:\fifa 16\Narrations\.studio\catalog.sqlite')
print('bin',[p.name for p in Path(FFMPEG).parent.iterdir()],flush=True)
paths=[r[0] for r in db.execute("SELECT wav FROM clips WHERE status='decoded' LIMIT 3")]
paths += [r[0] for r in db.execute('SELECT path FROM sources WHERE narrator IN (?,?) LIMIT 3',('Vilani','Luiz Roberto'))]
for source in paths:
    print('probe',source,flush=True)
    player=MciAudio()
    try:
        wav=prepare_preview(source,Path(r'U:\fifa 16\Narrations\.studio\preview_cache'),FFMPEG)
        player.load(wav)
        print(json.dumps(dict(loaded=str(wav),length=player.length,mode=player.mode)),flush=True)
        player.play();time.sleep(.05);player.pause();player.seek(min(100,player.length));player.stop()
        print('controls OK',flush=True)
    except Exception as exc:print('error',repr(exc),flush=True)
    finally:player.close()
for error in (16,272,320):
    message=ctypes.create_unicode_buffer(512)
    ctypes.windll.winmm.mciGetErrorStringW(error,message,len(message))
    print('error code',error,message.value,flush=True)
