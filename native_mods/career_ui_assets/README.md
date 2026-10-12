# Dedicated career calendar DDS icons (version 3)

The calendar's competition images live in `data/ui/imgAssets/careerCompetitionIcons/c<ID_VISUAL>.dds`.
The host's existing competition/stage resolution chooses the visual ID. This is not necessarily the
league ID or the raw career competition object ID. Official competition IDs are not remapped by
this module. `index.tsv` preserves the original host's ID availability through `host_available`:
1 accepts an initial ID; 0 avoids activating an old ambiguous alias which the host did not accept.
The module's `HasCompetition` export reads this availability from the new directory, allowing the
host's old DDS existence checks to fall back to the new catalogue without changing the ID order.
New IDs absent from the index are accepted when a valid dedicated DDS exists. Preseason identity
continues to use the guarded native competition registry.

`prepare_calendar_icons.py` copies the exact embedded DDS payload of each working `cmcomp_<ID>.big`.
It performs no resampling, recoloring or re-encoding. `index.tsv` records the source and DDS SHA-256.
The prepared images use DXT5/BC3, a 128x128 transparent canvas, and a proportional logo within the
upper-left 48x48 area. Center the logo within that 48x48 area, not within the whole canvas.

Guarded formatter adapters redirect `artAssets/cmCalendarCompetitions/cmcomp_<ID>.swf`/`.big`
and the legacy flat/light/dark DDS requests in the `cmCalendarCompetitions` namespace to the
dedicated DDS directory. There is no runtime league/light, league/dark or BIG scan
for these images. Existing images can be replaced directly; restart the game after changing DDSs.
Market/transfer events in `cmCalendar`, club crests, kit paths and the calendar screen stay unchanged.
Missing or malformed DDSs leave the original path untouched rather than redirecting to a broken file.
Existing BIGs remain as rollback/fallback resources, but successfully redirected icons do not use them.

The module preserves the installed version's goalkeeper-thumbnail alias compatibility and exports.
It requires FIFA 16 x64 timestamp `577DE45C`, the verified expanded-layout patches, and the original
formatter bytes. It refuses to overwrite other hooks. DLLs are pinned and activate on the next launch.

Preparation and installation from PowerShell:

```powershell
py -3 .\prepare_calendar_icons.py --source 'U:\fifa 16' --destination 'U:\mods\FIFA Friends V12'
.\build.cmd
.\Install-Game.ps1 -GameDirectory 'U:\fifa 16'
```

`build.cmd` tests the loader using a fixture with only the dedicated DDS directory: no league or BIG
resources are present. Tests cover ID bounds, bad/missing DDSs, path prefixes, unrelated UI paths,
formatter truncation, and native preseason identity. Installation backs up the previous module and
enabled list and provides `Restore-CalendarDds.ps1`. It does not replace `dinput8.dll`.

The runtime log `ModCarrerMode/logs/career_ui_assets.log` records `CATALOG`, `READY` and `RESOLVE`.
Actual calendar rendering must also be checked in the game; unit tests do not verify its display.
