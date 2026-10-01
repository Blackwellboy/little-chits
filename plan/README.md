# The Little Chits build plan

The plan is a queue of **41 small, verified tasks**. Together they take Little Chits from "it runs" to "two GPUs
running rival AI civilisations that produce X threads, image cards and clips on their own".

I (Claude) wrote each task's **spec** and its **acceptance tests** up front. Your local coding model does the
implementation. The gatekeeper, `scripts/plan.py`, only ticks a task off when all of the following hold:
- its tests pass
- the whole suite still passes
- every earlier task still passes
- the web app still builds
- nobody edited the tests

👉 Live checklist: [PROGRESS.md](PROGRESS.md)

## Run it with your local model

```bash
make install
# Aider + a local OpenAI-compatible coding model (llama.cpp / vLLM / LM Studio …)
pip install aider-chat
AGENT=aider MODEL=openai/<served-model-name> API_BASE=http://127.0.0.1:8080/v1 make plan-loop
```

For each task, the loop:
- gives the model the spec and rules
- runs the gates, with Aider feeding failures back until they pass
- ticks the task off and commits
- moves on to the next task

It stops, leaving a report in `plan/reports/`, if a task still fails after 4 attempts.

Other agents work too:
- `AGENT=opencode make plan-loop`
- `AGENT=custom AGENT_CMD='…"$PROMPT_FILE"…' make plan-loop`
- Or run it by hand: `make plan-next`, paste the prompt into any tool, then `python scripts/plan.py verify T05`
  and `python scripts/plan.py done T05 --commit`.

`ONLY=T08 make plan-loop` runs a single task.

**Tips for local coders:**
- Use the biggest coding model you have, with ≥32k context.
- Tasks are sized so one task fits comfortably in context.
- If a model stalls on a task, run it again with a different model: `ONLY=T10 MODEL=... make plan-loop`.

## Phases

| Phase | Tasks | You get |
|---|---|---|
| **0 · Foundation** | F1–F7 | the few guarantees that make comparisons credible: **play vs experiment** runs (no silent instinct fallback, frozen settings, run manifest, fail-closed saves), **per-decision records** + a persistent objective + stale-plan checks, **world/timeline identity**, a **bounded sequenced live stream**, **invariant tests**, **independent random streams** + "why didn't this happen" diagnostics, and **knowledge truth** (told vs worked, who told whom, lessons that cite memories) |
| **A · Run it on your GPUs** | T01–T04 | `make doctor`, a compact prompt for small models, `make dual` (5090 → World A, 3090 → World B), `make bench` to rank your GGUFs |
| **B · Free-thinking growth** | T05–T10 | chits **name their inventions**, choose **ambitions**, leave **signs** (the silent world's language), survive **storms and droughts**, found **named villages**; balance tuned so instinct is a fair baseline |
| **C · Story engine for X** | T11–T15 | evidence-backed **moments**, daily **chronicle** pages, a ready-to-post **X thread**, a **scoreboard card** image, and `make experiment` for headless model-vs-model runs packaged for posting |
| **D · Visuals for posts** | T16–T19 | a 🎬 **director camera** that cuts to the drama, **record mode** (16:9 / 9:16 / 1:1), weather, sign and village visuals, and `make clip` MP4 export |
| **E · True thinking & deep time** | T20–T23 | **open invention** (chits imagine new things and the world judges them by physical law, so each world grows its own tech tree), **beliefs, shrines and scripture** founded by the models themselves, a **deep ladder** from iron to engines, electricity and a **rocket** (big population needed, so it takes generations), and a **divergence report** with ready-to-post A-vs-B text |
| **F · Society & sandbox** | T24–T28, T30–T31, T34 (rivals: Age of Chitpires) | **jobs** (farmers, builders, scholars…), **trade and emergent money**, **chiefs, elections and laws** (elders in the silent world), **theft, guards and militias** (non-lethal), and **god mode**: drop artifacts (alien spaceship, holy book, meteor, musket…), bless, smite, plague, plus **save points**; **contact** (optional boats: a chit can sail to the other island and arrive as a stranger with its own model's mind), and **animals** (hunting, taming sheep for wool and cloaks, wolves on winter nights) |
| **G · Release** | T29, T33 | `make play` / `little-chits` CLI / Docker, a first-run welcome screen, "Play in 2 minutes" README; **shareable replays** (a single file anyone can open in a browser) |
| **C+ · Narrator** | T32 | one **narrator model** tells both worlds' days in the same voice (fair in model vs model), plus a weekly saga |

Tasks marked 🖐 in PROGRESS.md also need a quick manual check on the real GPUs once their gates pass.

## After the plan: the show
```bash
make dual                                   # both GPUs, both worlds, live at :8000
make experiment ARGS="--a http://127.0.0.1:18090/v1 --b http://127.0.0.1:18080/v1 --days 3"
# → data/experiments/<time>/summary.md, card.svg, thread text
make clip ARGS="--aspect 9:16 --seconds 30"  # a vertical MP4 for X
```

## For the plan author
Changed a spec or test? Run `python scripts/plan.py lock` to re-hash the acceptance files. Only the plan author
should do this, never the implementing agent.
