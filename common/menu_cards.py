"""Export editable career card PNGs to the legacy DDS format read by FIFA."""
from pathlib import Path
import io,struct
from PIL import Image,ImageOps,ImageChops


def export(source,destination,alpha_reference=None):
    image=ImageOps.fit(Image.open(source).convert('RGBA'),(1200,300),Image.Resampling.LANCZOS)
    if alpha_reference is not None:
        reference=ImageOps.fit(Image.open(alpha_reference).convert('RGBA'),image.size,Image.Resampling.LANCZOS)
        # Reuse the stock dressing-room fade. The minimum preserves any
        # existing cutouts and makes repeated exports idempotent.
        image.putalpha(ImageChops.darker(image.getchannel('A'),reference.getchannel('A')))
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    stream=io.BytesIO();image.save(stream,format='DDS',pixel_format='DXT5');raw=bytearray(stream.getvalue())
    struct.pack_into('<I',raw,20,len(raw)-128)
    # The stock UI loader treats a non-zero BPP as an uncompressed format even
    # when the FourCC says DXT5; that mismatch produced the green trophy tile.
    struct.pack_into('<I',raw,88,0)
    assert raw[84:88]==b'DXT5' and len(raw)==128+1200*300
    destination.write_bytes(raw);return image
