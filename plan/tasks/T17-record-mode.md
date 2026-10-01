# T17 · Record mode: clean frames for 16:9, 9:16 and 1:1 clips

**Why:** for X you want either a clean widescreen shot or a vertical phone clip, with no debug UI. Just the
world, a tasteful watermark, and captions that tell the story.

## Build
Create `web/src/ui/recordLayout.ts`, pure:

```ts
export type Aspect = "16:9" | "9:16" | "1:1";
export type RecordParams = { record: boolean; aspect: Aspect; world: "A" | "B" | "split"; director: boolean;
  captions: boolean; speed: number | null };
export function parseRecordParams(search: string): RecordParams
export function stageSize(aspect: Aspect, vw: number, vh: number): { width: number; height: number; left: number; top: number }
```
- **`parseRecordParams`**:
  - `?record=1` (or `true`) enables record mode.
  - `aspect` defaults to `"16:9"`, and anything invalid becomes `"16:9"`.
  - `world` is `A`/`B`/`split`, defaulting to `"A"`.
  - `director` and `captions` default to true in record mode and false otherwise; `=0` turns either off.
  - `speed` is a number from `1, 2, 5, 10, 25, 100`, else null.
- **`stageSize`** returns the largest box of that aspect that fits inside `vw×vh`, centred. All values are
  integers (floor).

**App** (`web/src/App.tsx`) in record mode:
- The stage is wrapped in a box sized by `stageSize`, on a black letterbox.
- Hide TopBar, SidePanel, Inspector, Minimap, Toasts and the vignette's heavy edges.
- Show a small watermark bottom-left: `LITTLE CHITS · World A · <brain label> · Day N`.
- On every in-game day change, show a day title card for 3 s (`Day 12 · Winter`, pixel font, centred).
- Show director captions (T16) as a lower-third.
- If `speed` is given, POST it to `/api/control` once.
- Force the director on when the param says so.

## Done when
`python scripts/plan.py verify T17` passes. 🖐 Then open `http://localhost:8000/?record=1&aspect=9:16&speed=5` and screen-record 30 s.
