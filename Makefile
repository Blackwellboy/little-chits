# Little Chits — common tasks
PY ?= python3
VENV = .venv
BIN = $(VENV)/bin
PORT ?= 8000

.PHONY: play play-single docker-desktop install web run open stop dual dual-doctor bench experiment lab clip compare doctor gpus diagnose shortcut dev test fake-model clean-data plan-status plan-next plan-loop

play:               ## the easy way: set up if needed, then start and open the browser (PORT=8010 to change the port)
	@test -d $(VENV) || $(MAKE) install
	@test -d web/dist || $(MAKE) web
	cd server && ../$(BIN)/python -m chits.cli --port $(PORT) $(ARGS)

play-single:        ## like play, but one world driven by one model
	@test -d $(VENV) || $(MAKE) install
	@test -d web/dist || $(MAKE) web
	cd server && ../$(BIN)/python -m chits.cli --port $(PORT) --mode single $(ARGS)

docker-desktop:     ## Docker Desktop on Windows or macOS (and Linux): CHITS_TOKEN=pick-a-secret make docker-desktop
	docker compose -f docker-compose.desktop.yml up --build

install:            ## python venv + web deps
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -e '.[dev]'
	cd web && npm install --no-audit --no-fund

web:                ## build the observer into web/dist (served by the API)
	cd web && npm run build

run: web            ## one process on http://localhost:8000 (world + observer)
	cd server && ../$(BIN)/uvicorn chits.app:app --host 0.0.0.0 --port $(PORT)

open:               ## start in the background (if needed) and open the browser: make open PORT=8010
	scripts/launch.sh $(PORT)

stop:               ## stop the server on PORT
	-fuser -k $(PORT)/tcp

dual:               ## both GPUs, one world each (edit configs/dual-gpu.json for your ports)
	CHITS_BRAINS_PRESET=../configs/dual-gpu.json $(MAKE) run

dual-doctor:        ## check both GPU servers answer and parse
	cd server && ../$(BIN)/python -m chits.tools.doctor --url $${A_URL:-http://127.0.0.1:18090/v1}; ../$(BIN)/python -m chits.tools.doctor --url $${B_URL:-http://127.0.0.1:18080/v1}

bench:              ## rank models on the same scenes: make bench ARGS="--url http://127.0.0.1:18191/v1 --url http://127.0.0.1:18192/v1"
	cd server && ../$(BIN)/python -m chits.tools.bench $(ARGS)

experiment:         ## model vs model headless, output ready to post: make experiment ARGS="--a http://127.0.0.1:18191/v1 --b http://127.0.0.1:18192/v1 --days 3"
	cd server && ../$(BIN)/python -m chits.tools.experiment $(ARGS)

lab:                ## the Experiment Lab (protocols, seeds x arms, blind report): make lab ARGS="run docs/protocols/speech-vs-silence.json --out runs/speech"
	PYTHONPATH=server $(BIN)/python -m chits.lab $(ARGS)

clip:               ## a timelapse MP4 for X from the running game: make clip ARGS="--aspect 9:16 --seconds 30"
	cd server && ../$(BIN)/python -m chits.tools.timelapse --url http://127.0.0.1:$(PORT) $(ARGS)

compare:            ## how differently the two worlds think (markdown; ARGS="--tweet" for a post): make compare PORT=8010
	cd server && ../$(BIN)/python -m chits.tools.compare --url http://127.0.0.1:$(PORT) $(ARGS)

doctor:             ## check a model answers, parses and is fast enough: make doctor ARGS="--url http://127.0.0.1:18191/v1"
	cd server && ../$(BIN)/python -m chits.tools.doctor $(ARGS)

gpus:               ## list GPUs and model servers, and whether each has enough parallel slots
	$(BIN)/python scripts/gpus.py

diagnose:           ## compact health report of the running game (models, plans, stuck chits, talk): make diagnose PORT=8010
	@curl -fs localhost:$(PORT)/api/diagnostics.txt || echo "Little Chits isn't running on port $(PORT)"

shortcut:           ## (re)install the desktop shortcuts: Windows via WSL, or Linux desktop + app menu (port 8010 unless PORT=)
	scripts/install-shortcut.sh $(if $(filter command line environment,$(origin PORT)),$(PORT),8010)

dev:                ## API on :8000 + hot-reloading observer on :5173
	(cd server && ../$(BIN)/uvicorn chits.app:app --host 0.0.0.0 --port $(PORT) --reload) & \
	(cd web && npm run dev)

test:
	$(BIN)/pytest -q

fake-model:         ## an OpenAI-compatible stand-in model on :18999, for trying things without a GPU
	$(BIN)/python tests/fake_llm.py --port 18999

clean-data:         ## start a brand new world next launch
	rm -rf server/data

plan-status:        ## the build plan checklist
	$(BIN)/python scripts/plan.py status

plan-next:          ## print the next task's prompt (paste into any coding agent)
	$(BIN)/python scripts/plan.py next

plan-loop:          ## let a local coding agent work through the plan (see plan/README.md)
	PY=$(BIN)/python scripts/agent_loop.sh
