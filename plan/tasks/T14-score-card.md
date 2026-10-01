# T14 · Scoreboard card: a 1200×675 image for X posts

**Why:** every thread needs an eye-catching image. A generated card showing Model A vs Model B, their
numbers and the moment of the day works even when you don't have a clip.

## Build
Create `server/chits/story/card.py`:

```python
def scoreboard_svg(worlds: list[dict], moment: dict | None = None, title: str = "LITTLE CHITS") -> str
```
- `worlds` has the same shape as in T13, with 1–2 entries. `moment` is a moment dict (`text`, `kind`) or None.
- Return a standalone SVG string:
  - `width="1200" height="675"` and a `viewBox`
  - a dark background with a subtle gradient
  - the title in a pixel-style font stack (`Silkscreen, monospace`)
  - `Day N`
- One column per world, coloured amber (`#ffb86b`) for direct and sky (`#7dd3fc`) for stigmergy. Each column
  shows:
  - the brain label as a large heading
  - the world name and culture ("can talk" / "silent")
  - big numbers for population, discoveries and buildings, each with its label
- A bottom banner with the moment text (✨ + text), wrapped to ≤ 2 lines of ≤ 70 characters with `…`.
- All text is XML-escaped (`&`, `<`, `>`, `"`). It must parse with `xml.etree.ElementTree`.
- Draw a few simple pixel chits (circles plus two eye rects) in each world's colour as decoration, so it
  doesn't look like a spreadsheet.

**API:**
- `GET /api/story/card.svg?since_day=1` returns `image/svg+xml` for the current worlds, with the top moment
  (reuse T13's builders).
- `GET /api/story/card.png` returns 501 with a JSON hint when `cairosvg` isn't installed. When it is installed
  (it's optional), convert the SVG with it.

**UI:** the "𝕏 Thread" modal from T13 shows the card (`<img src="/api/story/card.svg">`) above the posts, with a
Download link.

## Done when
`python scripts/plan.py verify T14` passes.
