"""Consistent small portraits for the selector and narration notification."""
from pathlib import Path
import hashlib
import uuid
from PIL import Image, ImageDraw, ImageOps


def portrait_image(path,name,size=68):
    with Image.open(path) as original:
        source=original.convert('RGBA')
    if name=='Vilani':
        source=source.crop((int(source.width*.27),int(source.height*.025),int(source.width*.76),int(source.height*.54)))
    elif name=='Luiz Roberto':
        source=source.crop((int(source.width*.25),int(source.height*.005),int(source.width*.76),int(source.height*.62)))
    photo=ImageOps.fit(source,(size,size),centering=(.5,.34))
    mask=Image.new('L',(size,size))
    ImageDraw.Draw(mask).ellipse((0,0,size-1,size-1),fill=255)
    photo.putalpha(mask)
    return photo


def cached_portrait(path,name,directory):
    source=Path(path); stat=source.stat()
    token=hashlib.sha256(f'{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{name}:v1'.encode()).hexdigest()[:24]
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    target=directory/(token+'.png')
    if not target.exists():
        image=Image.new('RGBA',(104,104))
        ImageDraw.Draw(image).ellipse((0,0,103,103),fill='white',outline='#dce5ee',width=2)
        image.alpha_composite(portrait_image(source,name,96),(4,4))
        temporary=directory/(token+'.'+uuid.uuid4().hex+'.png')
        try:
            image.save(temporary); temporary.replace(target)
        finally: temporary.unlink(missing_ok=True)
    return target
