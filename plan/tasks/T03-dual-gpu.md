# T03 · Dual-GPU profile: 5090 drives World A, 3090 drives World B

**Why:** a single command should start the model-vs-model show on both cards.

## Build
1. `configs/dual-gpu.json`, in the same format as `data/brains.json`:
   - Brain `rtx5090`, label `"RTX 5090"`, `base_url` `http://127.0.0.1:18090/v1`, `max_concurrency` 8.
   - Brain `rtx3090`, label `"RTX 3090"`, `base_url` `http://127.0.0.1:18080/v1`, `max_concurrency` 4.
   - `assign`: `{"A": "rtx5090", "B": "rtx3090"}`.
2. The runtime reads `CHITS_BRAINS_PRESET=<path>`. On startup, if the file exists, merge its brains and
   assignments into the Mind **before** worlds attach. They override brains with the same id, and the
   result is saved to `data/brains.json`. Implement this as `Mind.merge_preset(path: Path) -> None`, and
   call it from `Runtime.__init__` right after the Mind is created.
3. Makefile:
   - `dual:` runs `CHITS_BRAINS_PRESET=../configs/dual-gpu.json` + `make run`.
   - `dual-doctor:` runs `python -m chits.tools.doctor` on both URLs.
4. `scripts/start_dual.sh`, executable, POSIX sh:
   - checks both `/v1/models` endpoints with curl
   - prints which are up
   - starts `make dual`
   - keeps going if one card is down: that world runs on instinct, and the script prints a clear warning.
5. README: add a "Two GPUs, two minds" section with these commands.

## Done when
`python scripts/plan.py verify T03` passes. 🖐 Then, manually on the machine with both cards: `make dual`. The top bar shows "RTX 5090" and "RTX 3090".
