"""Read-only AFS2/AWB extraction, preserving IDs, offsets and full recordings."""
from pathlib import Path
import struct,io


def awb_entries(path):
    path=Path(path);size=path.stat().st_size
    with path.open('rb') as file:
        header=file.read(16)
        if len(header)!=16 or header[:4]!=b'AFS2':raise ValueError('Banco não é AFS2/AWB: '+str(path))
        offset_bytes,id_bytes=header[5],header[6]
        count,alignment,key=struct.unpack_from('<IHH',header,8)
        if offset_bytes not in (2,4,8) or id_bytes not in (1,2,4) or count>1000000 or not alignment:raise ValueError('Cabeçalho AWB inválido')
        ids=file.read(count*id_bytes); offsets=file.read((count+1)*offset_bytes)
        if len(ids)!=count*id_bytes or len(offsets)!=(count+1)*offset_bytes:raise ValueError('Índice AWB truncado')
        index_end=file.tell()
        for index in range(count):
            begin=int.from_bytes(offsets[index*offset_bytes:(index+1)*offset_bytes],'little')
            begin=(begin+alignment-1)//alignment*alignment
            end=int.from_bytes(offsets[(index+1)*offset_bytes:(index+2)*offset_bytes],'little')
            if begin<index_end or end<begin or end>size:raise ValueError('Referência AWB fora do arquivo')
            file.seek(begin);data=file.read(end-begin)
            yield dict(index=index,id=int.from_bytes(ids[index*id_bytes:(index+1)*id_bytes],'little'),offset=begin,size=end-begin,key=key,data=data)


def audio_header(data):
    if data[:2]==b'\x80\0' and len(data)>=20:
        channels=data[7];rate=struct.unpack_from('>I',data,8)[0];samples=struct.unpack_from('>I',data,12)[0]
        return dict(codec='adx',channels=channels,rate=rate,samples=samples,duration=samples/rate if rate else 0)
    clean=bytes(value&0x7f for value in data[:128])
    if clean[:3]==b'HCA':
        index=clean.find(b'fmt\0')
        if index>=0 and len(data)>=index+16:
            channels=data[index+4];rate=int.from_bytes(data[index+5:index+8],'big');blocks=int.from_bytes(data[index+8:index+12],'big')
            delay=int.from_bytes(data[index+12:index+14],'big');padding=int.from_bytes(data[index+14:index+16],'big')
            samples=max(0,blocks*1024-delay-padding)
            return dict(codec='hca',channels=channels,rate=rate,samples=samples,duration=samples/rate if rate else None)
        return dict(codec='hca',channels=0,rate=0,samples=0,duration=None)
    return dict(codec='auto',channels=0,rate=0,samples=0,duration=None,header=data[:32].hex())


def decode_frames(data):
    import av
    header=audio_header(data)
    if header['samples']==0 and header['codec']=='adx':return [],header
    with av.open(io.BytesIO(data),format=None if header['codec']=='auto' else header['codec']) as container:
        frames=list(container.decode(audio=0))
    if not frames:raise ValueError('Decoder não produziu amostras')
    actual=sum(f.samples for f in frames)
    # ADX padding can contain a final partial block. Retain the declared
    # duration, using the demuxer's normal trimming; never stretch a recording.
    rate=frames[0].sample_rate
    if header['duration'] is not None and abs(actual/rate-header['duration'])>.05:raise ValueError('Duração decodificada diverge da gravação')
    header.update(decoded_samples=actual,rate=rate,duration=actual/rate,channels=len(frames[0].layout.channels))
    return frames,header
