# Real-GPU checks, 2026-09-30

The build plan's manual checks (🖐 in `plan/PROGRESS.md`, which stays frozen) were run on the owner's go-ahead for
the **RTX 3090 only** (Ornith-1.5-35B-Q4_K_M on llama.cpp). The 5090 was in use elsewhere and was not touched, so
the checks that need it stay open. Code: `main` at `77984bb`. The live game was paused for T01, T04 and T15 so the
timings are the card's own, and restarted after.

| Check | What the plan asks | Result on the 3090 | Status |
|---|---|---|---|
| T01 doctor | `make doctor` prints OK | `OK · 3/3 valid · 1,832 ms · 49 tok/s · ~49 chits at 1x` | **Pass** (3090) |
| T03 dual-GPU | 5090 → A, 3090 → B | not run: needs the 5090 | **Open** |
| T04 model bench | bench your models | 3 repeats of the same model: score 86.7, 81.5, 83.0 (a 5.2-point spread from sampling alone); valid 100% each time; 22.7-26.5 s per scene because all 12 are sent at once | **Ran** (see note) |
| T15 experiment | a 1-day 5090-vs-3090 run, read `summary.md` | a 1-day **3090-vs-3090** run (`--mode versus`): 240 ticks in 374 s, 42 and 37 model plans, 0 failures, 40-46 s per reply with 24 chits on 8 slots; both worlds ended at 12 chits, 3 discoveries | **Partial**: the 5090 arm is open |
| T17 record mode | `?record=1&aspect=9:16&speed=5`, screen-record 30 s | the 9:16 frame renders letterboxed with no UI, captions and the world label only (checked in a GPU-rendered browser) | **Pass** |
| T18 visual FX | a storm at night should look dramatic | night tint, driving diagonal rain, lit windows and the furnace glowing; no lightning in the captured frame. Headless Chromium doesn't render night shading, so this was checked in a GPU-rendered browser, on a throwaway instance (god mode would mark the live run a sandbox) | **Pass** (drama is the owner's call) |
| T19 timelapse | `make clip` produces a playable MP4 | `clip-9x16.mp4`: H.264, 1080×1920, 30.0 s, decodes cleanly end to end, 47.7 MB (13 min to record with the test suite running beside it) | **Pass** |

## Notes

- **The bench measures style and noise** (research plan item 73): 45% of its score is valid JSON and 25% rewards
  the "experiment" and "social" verbs; one of its 12 scenes moves the score 3.75 points; the same model scored 81.5
  to 86.7 across repeats. Its latency includes queueing inside the server (a single doctor request took 1.8 s).
- **The 3090 can't carry both live worlds.** With World A moved onto it as well (141 chits), prompt processing fell
  to about 28 tokens/s under load, the model's architecture forces a full re-read of every ~3.5k-token prompt (no
  prefix cache reuse: "forcing full prompt re-processing ... SWA or hybrid/recurrent memory"), requests passed the
  90 s timeout and 38 of 40 failed. World A went back to instinct; World B alone recovered to ~5 s replies.
- Raw outputs are on the owner's machine (`manual-checks-20260930/`), not in the repo.
