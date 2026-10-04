"""Decision bench (run from server/: python ../tools/decbench.py build . items.json): the game's own one-letter choices, asked of several llama-servers, in two formats.

  build  SERVER_DIR OUT.json         real choice scenes from instinct worlds, plus clear-cut ones (starving with
                                     food in hand -> eat; exhausted at night -> sleep); options shuffled per item
  ask    ITEMS.json URL NAME FMT N   ask one server (FMT g = the game's prompt, j = JevK5's JSON layout) with N at
                                     once; writes answers to ITEMS.json.NAME.FMT.json
  score  ITEMS.json REF ANSWERS...   valid share, clear-cut accuracy, agreement with REF's answers, confidence, speed
"""
import json
import random
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

LETTERS = "ABCDEFGHIJKLMNOP"
J_SYSTEM = ("Apply the supplied criterion to the supplied evidence. Choose exactly one listed option. "
            "Respond with only its uppercase letter, with no explanation or reasoning.")


def build(server_dir, out):
    sys.path.insert(0, server_dir)
    from chits.brain import prompt as P
    from chits.brain.instinct import Instinct
    from chits.sim.actions import describe_step
    from chits.sim.world import World

    ins, items, rng = Instinct(), [], random.Random(7)

    def item(w, a, kind, want=None):
        opts = ins.options(w, a)
        if len(opts) < 3:
            return
        rng.shuffle(opts)
        right = None
        if want:
            hits = [i for i, o in enumerate(opts) if o["goal"] == want]
            if len(hits) != 1:
                return
            right = LETTERS[hits[0]]
        msgs = P.choice_messages(w, a, opts)
        user = msgs[1]["content"]
        evidence = user.split("\n\nYOUR OPTIONS:")[0]
        rows = [f"{o['goal']}: " + "; ".join(describe_step(s) for s in o["steps"][:6]) for o in opts]
        items.append({"id": len(items), "kind": kind, "n": len(opts), "right": right, "g": msgs,
                      "j": [{"role": "system", "content": J_SYSTEM},
                            {"role": "user", "content": json.dumps({
                                "evidence": evidence,
                                "criterion": f"Which plan should {a.name} carry out next, for its own needs and its village's?",
                                "options": [{"letter": LETTERS[i], "description": r} for i, r in enumerate(rows)]})}]})

    for seed in (42, 7, 24):
        w = World("A", "A", seed, "direct", 128, 18)

        def hook(world, a):
            if not a.plan:
                p = ins.plan(world, a)
                a.plan, a.goal = p["steps"], p["goal"]

        day = 0
        for stop in (3, 8, 15):
            while day < stop:
                for _ in range(240):
                    w.step(hook)
                day += 1
            chits = [a for a in w.agents.values() if not a.is_child(w.tick)][:8]
            for a in chits:
                a.brain = "bench"
                item(w, a, "real")
                keep = (a.hunger, a.energy, dict(a.inventory), w.tick)
                a.hunger = 4.0
                a.inventory["berries"] = a.inventory.get("berries", 0) + 2
                item(w, a, "starving", "eat")
                a.hunger, a.energy, a.inventory = 85.0, 3.0, dict(keep[2])
                w.tick = (w.tick // 240) * 240 + 230
                item(w, a, "exhausted", "sleep")
                a.hunger, a.energy, w.tick = keep[0], keep[1], keep[3]
                a.brain = "instinct"
    json.dump(items, open(out, "w"))
    print(len(items), "items:", {k: sum(1 for i in items if i["kind"] == k) for k in ("real", "starving", "exhausted")})


def ask(items_path, url, name, fmt, n):
    items = json.load(open(items_path))

    def one(it):
        body = {"model": "x", "messages": it[fmt], "max_tokens": 1, "temperature": 0, "logprobs": True,
                "top_logprobs": 20, "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t = time.time()
        try:
            res = json.loads(urllib.request.urlopen(req, timeout=300).read())
        except Exception as e:
            return {"id": it["id"], "error": str(e)[:200], "s": time.time() - t}
        ch = res["choices"][0]
        top = (ch.get("logprobs") or {}).get("content") or [{}]
        lp = {}
        for e in top[0].get("top_logprobs") or []:
            k = e["token"].strip().upper()
            if k in LETTERS[:it["n"]] and k not in lp:
                lp[k] = e["logprob"]
        text = (ch.get("message") or {}).get("content", "").strip().upper()[:1]
        return {"id": it["id"], "text": text, "lp": lp, "s": time.time() - t}

    t0 = time.time()
    with ThreadPoolExecutor(n) as ex:
        out = list(ex.map(one, items))
    json.dump({"name": name, "fmt": fmt, "wall": time.time() - t0, "answers": out},
              open(f"{items_path}.{name}.{fmt}.json", "w"))
    print(name, fmt, "done in", round(time.time() - t0, 1), "s", sum(1 for o in out if "error" in o), "errors")


def pick(o):
    import math
    if not o.get("lp"):
        return None, 0.0
    top = max(o["lp"].values())
    w = {k: math.exp(v - top) for k, v in o["lp"].items()}
    best = max(w, key=w.get)
    return best, w[best] / sum(w.values())


def score(items_path, ref_path, *paths):
    items = {i["id"]: i for i in json.load(open(items_path))}
    ref = {o["id"]: pick(o)[0] for o in json.load(open(ref_path))["answers"]}
    print(f"{'model':28} {'fmt':3} {'valid':>6} {'eat':>6} {'sleep':>6} {'agree':>6} {'conf':>5} {'p50 s':>6} {'wall':>6}")
    for p in (ref_path,) + paths:
        d = json.load(open(p))
        rows = d["answers"]
        picks = {o["id"]: pick(o) for o in rows}
        valid = sum(1 for o in rows if picks[o["id"]][0] is not None and o.get("text", "") == picks[o["id"]][0])
        acc = {}
        for kind in ("starving", "exhausted"):
            ks = [i for i in items.values() if i["kind"] == kind]
            acc[kind] = sum(1 for i in ks if picks[i["id"]][0] == i["right"]) / max(1, len(ks))
        real = [i for i in items.values() if i["kind"] == "real"]
        agree = sum(1 for i in real if picks[i["id"]][0] is not None and picks[i["id"]][0] == ref.get(i["id"])) / max(1, len(real))
        conf = statistics.mean(c for _, c in picks.values()) if picks else 0
        p50 = statistics.median(o["s"] for o in rows)
        print(f"{d['name'][:28]:28} {d['fmt']:3} {valid / len(rows):6.0%} {acc['starving']:6.0%} {acc['exhausted']:6.0%} "
              f"{agree:6.0%} {conf:5.2f} {p50:6.2f} {d['wall']:6.0f}")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "build":
        build(*args)
    elif cmd == "ask":
        ask(args[0], args[1], args[2], args[3], int(args[4]))
    else:
        score(*args)
