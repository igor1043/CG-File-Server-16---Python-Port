# CGFS 16 Server 16 Python Port v0.2.0

## Highlights

- Added stadium thumbnail support across the dashboard, `Assign Stadium`, and `Loading Stadium`.
- Improved the `Loading Stadium` modal layout with clearer progress, status text, and stadium name visibility.
- Refined floating secondary windows so assignment and editor dialogs open outside the main overlay flow.
- Expanded `Assign Stadium` browsing with stadium search, grouping, and larger visual previews.
- Improved documentation for stadium preview image organization inside stadium packs.

## Stadium Preview Images

Supported stadium preview images must follow this structure:

```text
StadiumGBD/<stadium name>/render/thumbnail/stadium/stadium.png
StadiumGBD/<stadium name>/render/thumbnail/stadium/stadium.jpg
StadiumGBD/<stadium name>/render/thumbnail/stadium/stadium.jpeg
```

The file name must be `stadium` and the folder name must match the assigned stadium folder exactly.

## Included Improvements

- Dashboard `Stadium Bay` preview integration
- `Assign Stadium` visual preview improvements
- Loading modal progress bar and stadium preview refinements
- Better handling for floating editor and assignment windows over FIFA 16
- README updates for contributors and mod pack authors
