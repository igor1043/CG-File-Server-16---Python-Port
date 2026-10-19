"""Country, league and club artwork from the installed FIFA database/assets."""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageOps
from .competition_catalog import nodes


def _first(paths):
    return next((path for path in paths if path.is_file()), None)


def artwork_path(game, kind, ident, catalog):
    if ident is None:
        return None
    game=Path(game);ident=int(ident);assets=game/'data/ui/imgAssets'
    if kind=='country':
        native=_first([assets/'flags512x512'/f'f_{ident}.dds',assets/'flags512x512'/f'f{ident}.dds'])
        if native:return native
        code=(catalog.get('nation_codes',{}).get(str(ident)) or '').strip().lower()
        name=(catalog.get('nations',{}).get(str(ident)) or '').casefold()
        if code=='gb':
            code=({'england':'gb-eng','inglaterra':'gb-eng','scotland':'gb-sct',
                   'escócia':'gb-sct','wales':'gb-wls','gales':'gb-wls',
                   'northern ireland':'gb-nir','irlanda do norte':'gb-nir'}.get(name,'gb-eng'))
        if code and all(c.isalpha() or c=='-' for c in code):
            return _first([Path(__file__).parent/'assets/flags'/f'{code}.png'])
        return None
    if kind=='league':
        objects=nodes(game)
        roots=[key for key,row in objects.items() if row[0]==3 and row[1]=='C'+str(ident)]
        if len(roots)==1:
            folder=assets/'careerCompetitionIcons'
            custom=_first([folder/(str(roots[0])+ext) for ext in ('.png','.jpg','.jpeg','.webp','.bmp','.dds')])
            if custom:return custom
            custom=_first([folder/'cards'/f'{roots[0]}.dds'])
            if custom:return custom
        return _first([assets/folder/variant/f'l{ident}.dds'
                       for folder in ('league','league512x128') for variant in ('light','dark','')])
    if kind=='team':
        team=next((row for row in catalog.get('teams',[]) if row['id']==ident),{})
        ids=list(dict.fromkeys([team.get('asset_id') or ident,ident]))
        return _first([assets/folder/variant/f'l{asset}.dds' for asset in ids
                       for folder in ('crest','crest64x64','crest50x50','crest32x32')
                       for variant in ('light','dark','')])
    return None


@lru_cache(maxsize=64)
def _load(path, stamp, size, width, height):
    with Image.open(path) as source:
        source=source.convert('RGBA')
        bounds=source.getchannel('A').getbbox()
        if not bounds:return None
        return ImageOps.contain(source.crop(bounds),(width,height),Image.Resampling.LANCZOS)


def artwork(game, kind, ident, catalog, size):
    try:
        path=artwork_path(game,kind,ident,catalog)
        if path:
            stat=path.stat()
            return _load(str(path),stat.st_mtime_ns,stat.st_size,*size)
    except (OSError,ValueError,KeyError,TypeError):
        pass
    return None
