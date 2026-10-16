"""Exercise MP3 preview conversion without playing audio on the speakers."""
import tempfile,wave,subprocess,json
from pathlib import Path
from core import FFMPEG,APP_ROOT
from audio_playback import MciAudio,prepare_preview

ffmpeg=Path(r'J:\mods\fifa 16\NarrationStudio\bin\ffmpeg.exe')
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder); original=root/'original.wav';mp3=root/'imported.mp3'
    with wave.open(str(original),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(44100);audio.writeframes(b'\0\0'*110250)
    subprocess.run([str(ffmpeg),'-loglevel','error','-y','-i',str(original),str(mp3)],check=True,creationflags=0x08000000)
    converted=prepare_preview(mp3,root/'cache',ffmpeg)
    player=MciAudio()
    try:
        player.load(converted)
        assert abs(player.length-2500)<=2,player.length
        player.seek(1725)
        assert abs(player.position-1725)<=1
        assert player.mode!='playing'
        print(json.dumps(dict(mp3_preview='verified',duration_ms=player.length,position_ms=player.position,audible_playback=False)))
    finally:player.close()
