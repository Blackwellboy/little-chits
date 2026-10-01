# Setting up your GPUs for Little Chits (step by step)

Your models feel slow because each model server answers one chit at a time while the others wait in line.
The fix is to restart each server with **parallel slots**, so 8 chits can think at once, and to pick models
that fit in each card's memory.

Everything below is typed into your **WSL terminal** (the "MAIN PC WSL" window). Copy each grey box, paste it
(right-click pastes in most terminals), and press Enter.

---

## Step 1 · Get the latest Little Chits

```bash
cd ~/projects/little-chits
git pull origin claude/dazzling-dijkstra-5nv6xh
```

## Step 2 · See what's running now

```bash
make gpus
```

This lists your GPUs and every model server it finds, with its **slots**:

- `slots=1` or `slots=2`: the server needs restarting with more slots, so carry on with this guide.
- `slots=8`: that one is already fine.

Now find the exact command each server was started with. The command includes the path of the model file:

```bash
ps -eo pid,args | grep -E "llama-server|vllm|ollama" | grep -v grep
```

Each line looks something like
`12345 /opt/llama.cpp/build/bin/llama-server -m /opt/models/SomeModel.gguf --port 18191 …`

Write down, for each server, the **port** (after `--port`) and the **model file** (after `-m`).

If nothing shows up here but `make gpus` did find servers, they're running on the Windows side (for example
LM Studio or a Windows llama.cpp). See "If your servers run in Windows" at the bottom.

## Step 3 · Stop the old servers

For each port you wrote down (change `18191` to your port):

```bash
fuser -k 18191/tcp
```

Run `make gpus` again. If a server comes straight back, something restarts it automatically (a service).
Find it and stop it:

```bash
systemctl --user list-units --all | grep -iE "llama|model|gguf"
systemctl --user stop NAME-FROM-THAT-LIST
```

## Step 4 · Pick a model for each GPU

See which GPU number is which card:

```bash
nvidia-smi -L
```

For example `GPU 0: NVIDIA GeForce RTX 5090` and `GPU 1: NVIDIA GeForce RTX 3090`.

List your model files with their sizes (change the folder if yours is elsewhere):

```bash
ls -lh ~/gguf
```

**The rule:** the file must be smaller than the card's memory minus about 6 GB, which leaves room for 8 chits
to think at once.

| Card | Memory | Largest model file |
|---|---|---|
| RTX 5090 | 32 GB | about **26 GB** |
| RTX 3090 | 24 GB | about **18 GB** |

If a model is too big, part of it runs on the CPU and it becomes very slow. That's probably why the 3090
showed 5 t/s.

Good choices, if you have them:
- **5090:** a Qwen3-30B-A3B (very fast), or a 14B–27B at Q4_K_M
- **3090:** an 8B–14B at Q4_K_M

## Step 5 · Start both servers the right way

Change the GPU numbers and model paths to yours from step 4:

```bash
scripts/gpu-server.sh --gpu 0 --port 18191 --model ~/gguf/YOUR-5090-MODEL.gguf
scripts/gpu-server.sh --gpu 1 --port 18192 --model ~/gguf/YOUR-3090-MODEL.gguf
```

Each one prints `Ready: http://127.0.0.1:18191/v1` when it has loaded, which can take a minute. It runs in
the background, and its log is in `data/gpu-18191.log`.

If it says it couldn't find `llama-server`, tell it where it is. The path is the first part of the lines you
saw in step 2:

```bash
export LLAMA_SERVER=~/llama.cpp/build/bin/llama-server
```

Then run the two commands again.

## Step 6 · Check it worked

```bash
make gpus
```

Both servers should now show **slots=8**.

## Step 7 · Start a game on them

1. Open the game (the desktop shortcut, or http://localhost:8010).
2. Press **⟲ new**, then **⚔ Model vs model**. Press **🔍 Find my models** if they aren't already picked, and
   make sure World A and World B each have a different server.
3. Press **Start**.
4. In **⚙ Brains**, keep **"Ask reasoning models to skip long thinking"** ticked. Thinking makes every decision
   several times slower and doesn't help much here.

## Step 8 · Check it's running smoothly

After a few in-game days:

```bash
make diagnose PORT=8010
```

Good looks like:
- no lines under **WARNINGS**
- **model share** above 80%
- **waiting on model** under 25%
- **throughput** in the hundreds of tok/s on the 5090

Anything wrong is explained in plain words at the top. Send it to Claude if you want help reading it.

---

### How fast does a model need to be?

Every chit wants a fresh plan about every **15 seconds** at 1× speed. A model that answers **N requests at
once** and takes **S seconds per answer** keeps up with about **N × 15 ÷ S chits**. With 8 slots that means:

| Seconds per decision (with 8 at once) | Keeps up with | What it's like |
|---|---|---|
| 2–3 s | 40–60 chits | lively: nearly every move is the model's own |
| 5–8 s | 15–25 chits | fine for a new world (18 chits); gets busier as it grows |
| 15 s or more | under 8 chits | **too slow**: most moves are instinct, and the world slows down to wait |

In tokens, aim for **at least 40 tokens/s per request** on a single answer (`make doctor` prints it). A
dense 27B on a 3090 manages about 20, which is too slow for more than a handful of chits. The game tells you:

- ⚙ **Brains** shows each model as **Fast enough** (green), **Borderline** (amber) or **Too slow** (red), for
  the number of chits it drives right now.
- `make diagnose PORT=8010` has a **speed:** line under each model, and a warning when it's too slow.
- The desktop launcher's window warns you when it starts.

If a model is too slow: use a faster model (below), give it more parallel slots, or start with fewer chits
(⟲ **new**, then **Chits per world**).

### Which models to use (tested on an RTX 5090 + RTX 3090 PC, 2026-09-28)

Measured with `make bench` (24 scenes, 8 at once) and `make doctor` on the RTX 3090:

| Model | Play score | Valid plans | Experiments | Keeps up with | Verdict |
|---|---|---|---|---|---|
| **Ornith-1.5-35B-A3B** Q4_K_M (22 GB) | **73** | **100%** | **21%** | **~39 chits** | best on the 3090 |
| Qwen3.8-27B OBLITERATED Q4_K_M (17 GB) | 73 | 100% | 4% | ~19 chits | good player, too slow |
| Ornith-1.5-9B Q6_K (7 GB) | 69 | 92% | 9% | ~26 chits | good small pick; the most social |
| Qwen3.5-9B Q6_K (7 GB) | 61 | 79% | 0% | ~27 chits | OK |
| Qwen3.6-35B-A3B "heretic" Q3_K_M | 35 | 25% | 0% | fast, but replies unusable | avoid |

**Why "A3B" models win:** a 35B-A3B is a *mixture of experts*. It knows as much as a big model but only uses
about 3B of its weights for each word, so it runs about as fast as a 3B model. Pick those for chits.
The 5090 runs qwen3.8-s on vLLM with 16 slots, which keeps up with a whole growing world.

To try another model, benchmark it against the ones you have:

```bash
make bench ARGS="--url http://127.0.0.1:18191/v1 --url http://127.0.0.1:18192/v1"
```

---

### If your servers run in Windows (LM Studio, Windows llama.cpp)

- **LM Studio:** open the Developer / Server tab and load the model. In its settings, set **Parallel requests**
  (or "Max concurrent predictions") to 8, and GPU offload to max. Tick "Serve on local network" only if WSL
  can't reach it.
- **Windows llama.cpp:** run the same flags as in step 5 in a Windows terminal:
  `llama-server.exe -m C:\path\model.gguf --port 18191 -ngl 99 -np 8 -c 32768 --jinja -fa on`
  (add `set CUDA_VISIBLE_DEVICES=1` first to pick the second GPU).

### Desktop shortcut: models and game with one double-click

`~/start-gpus.sh` is the one file that knows how to start (and stop) your model servers. The **Little Chits**
desktop shortcut runs it, then waits for the models, then starts the game.

**1. Install the shortcuts** (once, in your WSL terminal):

```bash
cd ~/projects/little-chits
make shortcut
```

If you didn't have a `~/start-gpus.sh`, this creates one from `scripts/start-gpus.example.sh`.

**2. Put your models in it** (once). Open it:

```bash
nano ~/start-gpus.sh
```

Change the two `gpu-server.sh` lines to your GPU numbers, ports and model files from steps 4 and 5. Then check
the `# model` lines near the top. There's one per server: `# model PORT NAME LOGFILE`, for example

```
# model 18191 5090 ~/projects/little-chits/data/gpu-18191.log
# model 18192 3090 ~/projects/little-chits/data/gpu-18192.log
```

The shortcut waits for those ports, and the NAME is what its window calls the model ("Starting the 3090
model…"). Save with **Ctrl+O**, **Enter**, then **Ctrl+X**. Try it:

```bash
~/start-gpus.sh
```

It only starts servers that aren't already running, so it's safe to run twice. `~/start-gpus.sh stop` stops them.
If a server runs somewhere else (vLLM in tmux, or a Windows llama-server), put whatever command starts it in
the `start)` part instead. It just has to be safe to run when the server is already up.

**3. Double-click Little Chits** on your Windows desktop. A small window shows:

- ✔ The 5090 model is ready. (or "Starting the 5090 model… 1 min so far" while it loads)
- ✔ The 5090 model gives good answers (1900 ms per decision). This is a real test decision, not just "is it on".
- ✔ The game is running.
- ✔ World A thinks with qwen3.8-s on the 5090.
- ✔ Opening the game in your browser…

Then it closes by itself. If anything goes wrong, the window stays open and says which log to read, for example
"The 3090 model didn't start. See data/gpu-18192.log". The full output of the last run is in
`%LOCALAPPDATA%\LittleChits\last-start.log`.

**Stop Little Chits** saves the world and stops the game. It asks first: **Yes** also stops the model servers
(frees the GPUs), **No** stops just the game (next start is faster), **Cancel** does nothing.

The shortcuts keep working after a reboot, a `git pull`, or moving the Little Chits folder. If they ever stop
working, run `make shortcut` again.
