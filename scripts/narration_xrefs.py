import sys, struct, json, re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py.memory_access import Memory
import pefile, capstone
OUT=Path(__file__).resolve().parents[1]/'artifacts/narration_research'
m=Memory();assert m.attack('fifa16')
pe=pefile.PE(r'U:\fifa 16\fifa16.exe',fast_load=True)
pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']])
functions=[(e.struct.BeginAddress,e.struct.EndAddress) for e in pe.DIRECTORY_ENTRY_EXCEPTION]
targets={int(x['address'],16):x['text'] for x in json.loads((OUT/'module_strings.json').read_text()) if any(t in x['text'] for t in ('audiodata/speechdata/%s/%s.sbs','SpeechVoice::SamplePlaybackDescription','Phrase::ChooseSample::pResults','por_br_bank'))}
dis=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
results=[]
for section in pe.sections:
    if not section.Characteristics&0x20000000:continue
    start=m.base_module+section.VirtualAddress
    data=m.read_process_memory(start,section.Misc_VirtualSize)
    for match in re.finditer(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]',data):
        p=match.start()
        target=start+p+7+struct.unpack_from('<i',data,p+3)[0]
        if target not in targets:continue
        rva=start+p-m.base_module
        fn=next(((a,b) for a,b in functions if a<=rva<b),(rva-150,rva+250))
        code=m.read_process_memory(m.base_module+fn[0],min(fn[1]-fn[0],16000))
        text='\n'.join(f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in dis.disasm(code,m.base_module+fn[0]))
        results.append(dict(target=targets[target],xref=hex(start+p),function=hex(m.base_module+fn[0]),end=hex(m.base_module+fn[1]),asm=text))
        print(targets[target],hex(start+p),hex(m.base_module+fn[0]),flush=True)
(OUT/'audio_xrefs.json').write_text(json.dumps(results,indent=2),encoding='utf8')
m.close()
