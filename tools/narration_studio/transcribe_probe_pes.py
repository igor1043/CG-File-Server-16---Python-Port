from pathlib import Path
from transcribe import whisper_model
model=whisper_model('small')
segments,info=model.transcribe(str(Path(__file__).parent/'pes_decode_probe.flac'),language='pt',beam_size=5,vad_filter=True,condition_on_previous_text=False)
print('duration',info.duration,flush=True)
for segment in segments:print(segment.text.encode('ascii',errors='backslashreplace').decode(),flush=True)
