"""Render all panel states without FIFA. Outputs must stay outside the repo."""
import argparse
import json
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_overlay_layout import panel_states, render_text
import test_career_overlay as fixtures
from server16_py.stadium_selector import StadiumSelector


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    output=parser.parse_args().output.resolve();output.mkdir(parents=True,exist_ok=True)
    records=[];thumbnails=[]
    with tempfile.TemporaryDirectory() as tmp:
        selector=fixtures.CareerOverlayTests().make_ready(Path(tmp))
        try:
            for controller in (False,True):
                selector.controller_connected=controller
                for name,panel in panel_states(selector):
                    image,text=render_text(panel)
                    name+= '-controller' if controller else '-keyboard'
                    image.save(output/(name+'.png'))
                    records.append(dict(name=name,size=list(image.size),texts=len(text)))
                    tile=Image.new('RGB',(310,390),'#e3e8ef')
                    image.thumbnail((300,352),Image.Resampling.LANCZOS)
                    tile.paste(image,((310-image.width)//2,28),image)
                    ImageDraw.Draw(tile).text((7,5),name,font=StadiumSelector.font(6),fill='#344651')
                    thumbnails.append(tile)
                selector.career_service.selected=selector.career_service.saves[0]
                selector.career_service.state='ready'
            selector.opened=True;selector.keyboard=True;selector.render()
            with Image.open(selector.shared.image_path) as image:image.save(output/'qwerty.png')
        finally:selector.shutdown()
    sheet=Image.new('RGB',(310*6,390*((len(thumbnails)+5)//6)),'#e3e8ef')
    for i,tile in enumerate(thumbnails):sheet.paste(tile,((i%6)*310,(i//6)*390))
    sheet.save(output/'all-panels.png')
    (output/'manifest.json').write_text(json.dumps(records,indent=2),encoding='utf8')
    print(json.dumps(dict(panels=len(records),output=str(output))))


if __name__=='__main__':main()
