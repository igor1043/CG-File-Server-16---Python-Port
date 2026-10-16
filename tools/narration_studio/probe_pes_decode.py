from pathlib import Path
import io,struct,json,time
import av,numpy as np

awb=Path(r'J:\mods\pes\audio pes\content\Multinarrador\Luis Roberto\sound\awb\20_MAIN.awb')
with awb.open('rb') as file:
    head=file.read(16);count,alignment,key=struct.unpack_from('<IHH',head,8)
    ids=file.read(count*head[6]);offsets=file.read((count+1)*head[5])
    entries=[]
    for i in range(count):
        begin=int.from_bytes(offsets[i*head[5]:(i+1)*head[5]],'little');begin=(begin+alignment-1)//alignment*alignment
        end=int.from_bytes(offsets[(i+1)*head[5]:(i+2)*head[5]],'little')
        entries.append((end-begin,begin,i))
    for size,begin,i in sorted(entries,reverse=True)[:3]:
        file.seek(begin);raw=file.read(size);started=time.perf_counter()
        container=av.open(io.BytesIO(raw),format='adx')
        frames=list(container.decode(audio=0));rate=frames[0].sample_rate;length=sum(f.samples for f in frames)/rate
        output=Path(__file__).parent/'pes_decode_probe.flac'
        with av.open(str(output),'w',format='flac') as out:
            stream=out.add_stream('flac',rate=rate);stream.layout=frames[0].layout
            for frame in frames:
                for packet in stream.encode(frame):out.mux(packet)
            for packet in stream.encode(None):out.mux(packet)
        pcm=np.concatenate([f.to_ndarray().ravel() for f in frames]);peak=float(np.max(np.abs(pcm.astype('float32'))))
        print(json.dumps(dict(id=i,adx=size,flac=output.stat().st_size,duration=length,rate=rate,peak=peak,seconds=time.perf_counter()-started)),flush=True)
