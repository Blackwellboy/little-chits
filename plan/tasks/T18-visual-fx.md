# T18 · New visuals: weather, signs, villages, title cards

**Why:** T07–T09 added signs, weather and villages. Now they need to *look* great on camera.

## Build
Create `web/src/render/fx.ts`, pure data plus helpers with no pixi imports:

```ts
export type WeatherProfile = { particles: "rain" | "snow" | "leaves" | "petals" | "fireflies" | "none";
  count: number; tint: number; tintAlpha: number; lightning: boolean; wind: number };
export function weatherProfile(weather: string, season: string): WeatherProfile
export function signGlyph(symbol: string): string
export function villageLabelVisible(zoom: number): boolean
```
- **`weatherProfile`** follows this table. Seasons only matter when the weather is `clear`.

  | weather | particles | count | tint | tintAlpha | lightning | wind |
  |---|---|---|---|---|---|---|
  | rain | rain | 220 | 0x3a4a6a | 0.18 | false | 0.6 |
  | storm | rain | 420 | 0x1a2238 | 0.38 | true | 2.2 |
  | drought | none | 0 | 0xd9a441 | 0.14 | false | 0.2 |
  | snow | snow | 260 | 0xdfe8ff | 0.10 | false | 0.4 |
  | clear + winter | snow | 120 | 0 | 0 | false | 0.3 |
  | clear + autumn | leaves | 45 | 0 | 0 | false | 0.8 |
  | clear + spring | petals | 25 | 0 | 0 | false | 0.5 |
  | clear + summer | fireflies | 30 | 0 | 0 | false | 0 |

  Anything unknown returns particles `none`, count 0, tint 0, tintAlpha 0, lightning false, wind 0.
- **`signGlyph`**: food 🫐, wood 🪵, stone 🪨, clay 🟫, ore 🟠, fish 🐟, danger ⚠️, home 🏠, build 🔨,
  meet 👋, else ❔.
- **`villageLabelVisible(zoom)`** is true when `zoom < 2.6`.

**`WorldView.ts`** uses these:
- Replace the season-only weather setup with `weatherProfile(clock.weather, clock.season)`:
  - rain is angled streaks
  - storms get a lightning flash every 4–9 s (a full-screen white overlay fading out over ~250 ms) plus the
    darker tint
  - drought gets a warm tint and a slight shimmer
- Draw signs (from `WorldData.signs`, which the snapshot and frames from T07 fill): a small wooden post sprite
  (painted in `art.ts`) with the glyph above it in screen space when zoom > 1.5.
- Village names: poll `/api/worlds/{id}/settlements` every 10 s and draw the name in the pixel font at each
  centroid, large and semi-transparent, only when `villageLabelVisible(zoom)`.
- Day title card: when `clock.day` changes, show `Day N · Season` centred for 2.5 s in normal mode too, with a
  subtle fade.

## Done when
`python scripts/plan.py verify T18` passes. 🖐 Then check a screenshot: a storm at night should look dramatic.
