"""Render the real card without opening FIFA, injecting DLLs or game input.

Usage: python tests/render_selector_preview.py [stadium-jpg] [club-logo]
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from server16_py.stadium_catalog import StadiumEntry
from server16_py.stadium_selector import StadiumSelector


def main():
    root=Path(__file__).resolve().parents[1]/'build'/'stadium-selector-preview'
    preview=Path(sys.argv[1]) if len(sys.argv)>1 else None
    crest=Path(sys.argv[2]) if len(sys.argv)>2 else None
    app=SimpleNamespace(base_dir=root,log=lambda *args:None,
                        _resolve_team_logo_path=lambda team_id:crest)
    with patch('server16_py.stadium_selector.SELECTOR_MAPPING_NAME',f'Local\\CGFS16_DesignPreview_{os.getpid()}'), \
            patch('server16_py.crowd_control.MAPPING_NAME',f'Local\\CGFS16_CrowdPreview_{os.getpid()}'):
        selector=StadiumSelector(app)
    try:
        from server16_py.prematch_panel import PrematchPanel
        from shutil import copyfile
        selector.opened=True
        selector.prematch_panel=PrematchPanel(selector)
        selector.render()
        copyfile(selector.shared.image_path,root/'prematch-menu-preview.png')
        selector.controller_connected=True
        selector.render()
        copyfile(selector.shared.image_path,root/'prematch-menu-xbox-preview.png')
        from server16_py.match_settings_panel import MatchSettingsPanel
        selector.prematch_panel=MatchSettingsPanel(selector)
        selector.render()
        copyfile(selector.shared.image_path,root/'match-settings-preview.png')
        selector.controller_connected=False
        selector.crowd_control.shared.current_percent=65
        selector.crowd_control.shared.automatic_percent=65
        selector.crowd_control.shared.ack=selector.crowd_control.shared.command
        selector.prematch_panel=PrematchPanel(selector,crowd=True)
        selector.render()
        copyfile(selector.shared.image_path,root/'crowd-panel-preview.png')
        selector.prematch_panel=None
        selector.entries=[StadiumEntry('BRA - Maracanã - Flamengo','BRA','Maracanã - Flamengo','Flamengo','1043',root,preview)]
        selector.entries*=3
        selector.opened=True; selector.focus=2; selector.index=1
        selector.refresh()
        if preview:
            import time
            deadline=time.monotonic()+5
            while selector._preview_loading and time.monotonic()<deadline:
                selector._drain_images(); time.sleep(0.01)
        print(selector.shared.image_path)
        copyfile(selector.shared.image_path,root/'stadium-card-preview.png')
        selector.focus=3; selector.render()
        copyfile(selector.shared.image_path,root/'apply-focused-preview.png')
        selector.focus=2
        selector.keyboard=True; selector.focus=0; selector.key_index=39
        selector.render()
        print(selector.shared.image_path)
        copyfile(selector.shared.image_path,root/'keyboard-preview.png')
        from server16_py.match_audio_panel import MatchAudioPanel
        app.exedir=root/'audio-preview-game'
        app.HID,app.AID='1043','545'
        app._resolve_team_name=lambda team_id:{'1043':'Flamengo','545':'Fluminense'}.get(team_id,'')
        app.settings=SimpleNamespace(crowd_master_volume=1.,goal_master_volume=1.)
        selector.keyboard=False
        selector.audio_panel=MatchAudioPanel(selector)
        selector.audio_panel.values=[75,50]
        selector.render()
        audio=root/'match-audio-preview.png'
        copyfile(selector.shared.image_path,audio)
        selector.controller_connected=True
        selector.render()
        copyfile(selector.shared.image_path,root/'match-audio-xbox-preview.png')
        selector.controller_connected=False
        print(audio)
        selector.audio_panel.runtime.save_match((.75,.5))
        selector.audio_panel=MatchAudioPanel(selector)
        selector.audio_panel.focus=4
        selector.render()
        audio_profile=root/'match-audio-profile-preview.png'
        copyfile(selector.shared.image_path,audio_profile)
        print(audio_profile)
    finally:
        selector.shutdown()


if __name__=='__main__':
    main()
