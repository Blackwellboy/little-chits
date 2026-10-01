# T29 · Plug-and-play release

**Why:** anyone with a GPU should get from `git clone` to watching their own model raise a civilisation next to
the baseline in a couple of minutes, with no config files. The first-run autodetect already exists
(`Runtime.autodetect`: two servers found → **model vs model** on the same island; one → a **single model**
world), and game modes are chosen in ⟲ New game (`versus`, `single`, `culture`). This task wraps it in a
one-command launcher, Docker, and a welcome screen.

## Build
1. **CLI:** `server/chits/cli.py` with `build_parser() -> argparse.ArgumentParser` and `main(argv=None)`.
   - Flags:
     - `--port` (default 8000)
     - `--host` (default 127.0.0.1)
     - `--data` (sets `CHITS_DATA_DIR`)
     - `--model URL` (sets `CHITS_MODEL_URL`)
     - `--mode versus|single|culture` (sets `CHITS_MODE`)
     - `--no-scan` (sets `CHITS_AUTODETECT=0`)
     - `--no-browser`
     - `--speed N` (sets `CHITS_SPEED`)
   - `main` sets the env vars, opens the browser after startup unless `--no-browser`, and runs uvicorn on
     `chits.app:app`.
   - In `pyproject.toml`: `[project.scripts] little-chits = "chits.cli:main"`.
2. **Make targets.**
   - `make play` = install (if `.venv` is missing) + build the web app (if `web/dist` is missing) + run via
     the CLI.
   - `make play-single` passes `--mode single`.
3. **Docker.**
   - A `Dockerfile` (multi-stage: node builds `web/dist`, python:3.12-slim runs the CLI with `--host 0.0.0.0
     --no-browser`) with `EXPOSE 8000`.
   - A `docker-compose.yml` with `network_mode: host` (so model servers on the host's localhost are found)
     and a `./data` volume.
4. **Health.** `/api/health` already reports `mode`, `first_run` and `autodetected`. Add `"brains"`:
   `{world id: brain label}`.
5. **Welcome screen.** On the first visit (localStorage `chits:welcomed` unset), the web app shows a welcome
   card. It includes:
   - a one-paragraph explanation
   - what was detected: "Found **qwen3-14b** on :18090 and **gemma-27b** on :18080: model vs model on the
     same island." / "Found **qwen3-14b** on :18090: single-model world." / "No model found. Start
     llama-server / Ollama / LM Studio, then press 🔍 Scan in ⚙ Brains"
   - buttons: **Watch** (close), **Open Brains**, **New game** (opens the mode chooser)
6. **README.** A new top section, "Play in 2 minutes", with exactly three commands (clone, `make play`,
   open), plus a Docker alternative and a short troubleshooting list:
   - port in use → `--port`
   - model not found → the Brains scan
   - the model is slow → lower `CHITS_PER_WORLD`

**Security (added after review):**
- Keep binding to 127.0.0.1 by default.
- `CHITS_TOKEN` (or `--token`): when set, every non-GET API call and the WebSocket need
  `Authorization: Bearer <token>` (or `?token=`), otherwise 401. The web app reads the token from
  `?token=` once and keeps it in localStorage.
- Starting with a non-loopback `--host` and no token refuses to start unless `--insecure`, with a clear
  message.
- The README documents Docker separately for Linux (`network_mode: host`) and Docker Desktop on Windows/macOS
  (use `host.docker.internal` URLs). For Windows it recommends the native WSL launcher.
- See `plan/acceptance/test_t29b_security.py`.

## Done when
`python scripts/plan.py verify T29` passes. 🖐 Then try it from a fresh clone on a machine with a model running.
