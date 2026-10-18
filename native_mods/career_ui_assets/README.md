# Unified career competition artwork (revision 4)

User-editable sources are `data/ui/imgAssets/careerCompetitionIcons/<INI_ID>.png`.
The current CompData hierarchy supplies the main competition ID that is also used
in FSW's installed INI. Server16 prepares two proportional DDS views from that
same source: `calendar/c<ID>.dds` and `cards/c<ID>.dds`. Both are distributed with
the PNGs and `competitions.tsv`. A package installation works without launching
Server16; only changing PNGs requires preparation before the next FIFA launch.

The calendar, Central next-match card and competition next/results cards use
one identity resolver. A live career's object number is never interpreted using
another release's on-disk object numbering. Its semantic visual identity maps
to the current installed competition ID. CalendarCell's reference fields are
`competition`, `stage`, **`fixture ID`**; the third field never participates in
competition lookup. This fixes the month-dependent Portuguese/English cup icons.

Internally the host tags explicitly resolved IDs with 1000000 to distinguish them
from stock visual IDs passed through the same FIFA formatters. This is an internal
UI namespace, not a second editable ID or table. The emitted path strips the tag
and always names the INI ID in the shared folder. Unrelated crests/kits/stadium
paths retain their behavior. Legacy league light/dark requests resolve through
the manifest only when the visual identity is unambiguous.

Legacy `cmcomp_<ID>.big/.swf` strings are recognized at the formatter boundary;
no BIG is opened, scanned, extracted or rebuilt for competition icons. Missing
calendar artwork routes to a transparent DDS, not an old BIG. Screen/layout BIGs
and the separate stadium-photo movie writer are unrelated resources.

Build: `build.cmd`; tests use synthetic DDSs with no BIG or league directories,
check the shared identity contract, formatter bounds and keeper regressions.
The host regression test `career_native/scripts/tests/test_calendar_icon_identity.cmd`
checks all 65535 fixture IDs for four competitions from the captured old career.
`career_ui_assets.log` records CATALOG/READY/RESOLVE. Visual verification of all
three screens is required after installation; unit tests do not prove rendering.

The package installer distributes the library while preserving user-edited PNGs
and their matching generated views. The source-only export intentionally excludes
images; use the full FIFA Friends package for a ready-to-run installation.

## Career Starting XI goalkeeper (14 October 2026)

StartingXIDP reads one SHARED team-kit selector at team-sheet offset `+8`.
The goalkeeper interprets `-1` as unsigned team `262143`; the outfield branch
already treats negative selectors as automatic team selection. The initial
repair incorrectly wrote `(TeamID << 14) | 2` into that shared field, making
all eleven players request the keeper kit. This regression was reported in-game.

The final repair normalizes only `UINT32_MAX` to ZERO in a local `0x2DC`-byte
sheet copy. Zero restores the native role-specific behavior: the keeper uses
kit type 2 and the ten outfield players use type 0 for the sheet's own TeamID.
It never writes the positive keeper key to the shared selector. Saved sheets,
valid existing overrides and all other fields remain unchanged.

`keeper_pitch_hook.inc` wraps only the StartingXIDP serializer call at native
RVA `40B59F2`, on x64 timestamp `577DE45C`, with exact live signatures checked
before installing. No DDS, APT or BIG replacement is needed.

`test_keeper_pitch_sheet.c` now executes the actual native x64 keeper and
outfield instruction sequences from `keeper_native_branches.h`. It reproduces
both the original invalid-team failure and the all-keepers regression, then
verifies all eleven rows for seven clubs with sentinel and automatic selectors.
The ten outfield results must match their original native results exactly.
The same tests compare all eleven outputs with the signed fallback branches
read directly from the user-opened mod backup (PID 38504).
The original source, valid keys, invalid teams and unrelated bytes are checked.
`build.cmd` runs these tests and the existing UI asset resolver tests.

The user-provided original and mod backups have matching executable hashes.
The current Starting XI bytecode matches both; pitch/player resources and
Flamengo's team/kit records match the mod backup, including keeper teamkitid
1692. The issue is the shared selector's runtime interpretation. The live backup
uses a signed <=0 fallback; the current expanded-ID path checks only zero.
Normalizing the sentinel restores the reference behavior for both roles.

The production module is `ModCarrerMode/mods/career_ui_assets/career_ui_assets.dll`.
Installation preserves the DLL's existing public exports and the calendar
resolver. A restart loads the corrected module; a process with restricted RAM
access cannot be updated live from this session. On 14 October 2026, the user
confirmed the final correction in-game. Earlier APT and native experiments are archived
in the study directory and are not included in the production build.

The international crowd change remains separate: a six-point bonus for type-1
confederations and the type-0 FIFA world node, preserving the 90-percent cap
and manual overrides. Domestic and preseason country nodes receive no bonus.

## Squad management and formations goalkeeper (17 October 2026)

The root fix is now in `career_native/src/host/swiss_byte_patches.h`: all SIX
keeper entries retain the original signed JLE automatic fallback while retaining
the unsigned shift for positive packed IDs. The central unsigned-key adaptation
previously changed JLE to JE, converting the automatic -1 into team 262143.
This affects five Squad-family producers plus the Starting XI serializer. The
visible active Squad path is RVA `409ACB5`, distinct from the saved-roster paths.
The two local guards below remain compatible with corrected central descriptors.
`career_native/scripts/tests/test_keeper_auto_keys.cmd` executes all six actual
native keeper branches using the production byte table, seven clubs and six
selectors. The Starting XI signature check accepts both the older JE and the
corrected JLE, requiring the rest of the live branch to match exactly.

The editable roster and formation screens have two separate producers, both
different from StartingXIDP. Both requested `2_262143_0` for the keeper while the
ten outfield rows correctly requested `0_1043_0` for Flamengo. Formation uses
the branch at RVA `40948A5`; the editable roster uses RVA `409979E`. Repairing
one does not cover the other, and the Starting XI serializer covers neither.

`keeper_squad_hook.inc` validates the x64 executable timestamp and the complete
31-byte formation and 24-byte roster branches, then changes their conditional
opcodes at `40948AD` and `40997A3` from JE to JLE. A nonpositive selector now uses the native sheet TeamID, matching
the outfield branch. Positive explicit selectors retain their native decoding.
The branch length, target, source sheet and ten outfield instructions are untouched.
The installer accepts an already corrected branch and rejects other signatures.
`Fifa16UiAssetsSquadKeeperReady` reports activation independently of Starting XI.

`test_keeper_squad.c` executes both captured native x64 branches for all eleven
positions on BOTH screens, seven club IDs, automatic, negative and positive explicit selectors.
It reproduces the original keeper's invalid team, verifies type 2 for the keeper
and type 0 for automatic outfield rows, preserves positive overrides and source
sheets, and tests signature rejection. `build.cmd` runs it alongside the existing
Starting XI and calendar tests. The normal worker now requires all three repairs
before reporting READY. No image, lineup or career-save replacement is involved.
