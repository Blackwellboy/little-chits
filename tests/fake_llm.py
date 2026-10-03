"""A fake OpenAI-compatible model server for end-to-end tests (no GPU needed).

It reads the scene text like a (not very bright) model would and replies with
plans in the messy formats real local models produce: <think> blocks, ```json
fences, trailing commas, bare strings, and the occasional unusable reply.

    python tests/fake_llm.py --port 18999
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
STATE = {"calls": 0, "latency": 0.3, "garbage_rate": 0.05, "seeded": 0}  # (seeded: requests that carried a seed)


def _plan_for(scene: str, rng: random.Random) -> dict:
    hunger = int(re.search(r"Hunger (\d+)", scene).group(1)) if "Hunger" in scene else 60
    carrying = re.search(r"Carrying \(\d+/\d+\): (.*?)\.\n", scene)
    items = []
    if carrying and carrying.group(1) != "nothing":
        for part in carrying.group(1).split(", "):
            m = re.match(r"(\d+) (.+)", part)
            if m:
                items += [m.group(2)] * min(2, int(m.group(1)))
    if hunger < 40:
        return {"thought": "My belly aches. Food first.", "goal": "eat",
                "plan": [{"do": "gather", "what": "berries", "qty": 5}, {"do": "eat"}]}
    if "CONSTRUCTION SITE" in scene and rng.random() < 0.5:
        sid = re.search(r"CONSTRUCTION SITE (\S+):", scene).group(1)
        need = re.search(r"still needs (\d+) ([a-z ]+)", scene)
        steps = []
        if need:
            steps.append({"do": "gather", "what": need.group(2).strip(), "qty": int(need.group(1))})
        steps.append({"do": "help", "site": sid})
        return {"thought": "Someone is building nearby; I'll lend a hand.", "goal": "help build", "plan": steps}
    if "You have no home yet" in scene and rng.random() < 0.6:
        return {"thought": "I need a hut before the cold comes.", "goal": "build a hut",
                "plan": [{"do": "gather", "what": "wood", "qty": 8}, {"do": "gather", "what": "fiber", "qty": 4},
                         {"do": "build", "what": "hut"}]}
    r = rng.random()
    if r < 0.35:
        pool = items + ["stone", "wood", "fiber"]
        combo = rng.sample(pool, k=min(len(pool), rng.choice([2, 3])))
        pre = [{"do": "gather", "what": c, "qty": 1} for c in combo if c not in items][:2]
        return {"thought": "A sharp edge bound to a handle might cut better…", "goal": "invent a tool",
                "plan": pre + [{"do": "experiment", "with": combo}]}
    if r < 0.5 and "can talk" in scene:
        return {"thought": "I should tell the others what I've seen.", "goal": "share news",
                "plan": [{"do": "say", "to": "all", "text": "There is clay by the river, and berries to the north!"}]}
    if r < 0.6:
        return {"thought": "What's beyond those hills?", "goal": "explore",
                "plan": [{"do": "explore", "dir": rng.choice(["N", "S", "E", "W"])}]}
    what = rng.choice(["wood", "stone", "fiber", "clay"])
    return {"thought": f"We'll always need {what}.", "goal": f"collect {what}",
            "plan": [{"do": "gather", "what": what, "qty": 6}, {"do": "store", "what": "all"}]}


def _render(obj: dict, rng: random.Random) -> str:
    s = json.dumps(obj)
    style = rng.random()
    if style < 0.2:
        return f"<think>Let me consider my options carefully...</think>\n{s}"
    if style < 0.4:
        return f"Here is my plan:\n```json\n{json.dumps(obj, indent=2)}\n```"
    if style < 0.5:
        return s[:-2] + "],}" if s.endswith("]}") else s  # trailing comma
    if style < 0.55:
        o = dict(obj)
        o["plan"] = [f"{st['do']} {st.get('what', '')} {st.get('qty', '')}".strip() for st in obj["plan"]]
        return json.dumps(o)
    return s


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "fake-chit-7b", "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    STATE["calls"] += 1
    STATE["seeded"] += "seed" in body
    rng = random.Random(STATE["calls"])
    await asyncio.sleep(STATE["latency"] * rng.uniform(0.5, 1.5))
    msgs = body.get("messages", [])
    user = msgs[-1]["content"] if msgs else ""
    system = msgs[0]["content"] if msgs else ""
    # opt-in server quirks, for the Test button's diagnosis (tests/test_brain_checkup.py)
    if STATE.get("refuse_json") and "response_format" in body:  # as LM Studio does (issue #61)
        return JSONResponse({"error": {"message": "'response_format.type' must be 'json_schema' or 'text'"}}, 422)
    if STATE.get("refuse_switch") and "chat_template_kwargs" in body:
        return JSONResponse({"error": {"message": "unknown field: chat_template_kwargs"}}, 400)
    if STATE.get("thinks") and (body.get("chat_template_kwargs") or {}).get("enable_thinking") is not False:
        # a reasoning model: the whole reply goes on thinking unless it is asked not to
        return JSONResponse({"id": f"fake-{STATE['calls']}", "object": "chat.completion", "created": int(time.time()),
                             "model": body.get("model", "fake-chit-7b"),
                             "choices": [{"index": 0, "finish_reason": "length", "message": {
                                 "role": "assistant", "content": "", "reasoning_content": "Let me think about what a chit would"}}],
                             "usage": {"prompt_tokens": len(user) // 4, "completion_tokens": body.get("max_tokens", 1)}})
    if STATE.get("letters") and body.get("max_tokens") == 1:
        # a one-token choice, with logprobs when asked (opt-in: the tests of the mind's own handling leave it off)
        choice = {"index": 0, "message": {"role": "assistant", "content": "A"}, "finish_reason": "length"}
        if body.get("logprobs") and STATE.get("logprobs", True):
            choice["logprobs"] = {"content": [{"token": "A", "logprob": -0.1, "top_logprobs": [
                {"token": "A", "logprob": -0.1}, {"token": "B", "logprob": -2.6}, {"token": " the", "logprob": -5.0}]}]}
        return JSONResponse({"id": f"fake-{STATE['calls']}", "object": "chat.completion", "created": int(time.time()),
                             "model": body.get("model", "fake-chit-7b"), "choices": [choice],
                             "usage": {"prompt_tokens": len(user) // 4, "completion_tokens": 1}})
    if "reflecting" in system:
        text = json.dumps({"lessons": ["Gathering food before dark keeps me alive.",
                                        "Working beside others finishes buildings faster."],
                           "ambition": "Build a warm home for everyone before winter"})
    elif "Reply exactly" in user:
        text = '{"ok": true, "word": "chit"}'
    elif rng.random() < STATE["garbage_rate"]:
        text = "I think I will go and look for some berries, maybe."
    else:
        plan = _plan_for(user + system, rng)
        text = json.dumps(plan) if STATE.get("tidy") else _render(plan, rng)
    return JSONResponse({
        "id": f"fake-{STATE['calls']}", "object": "chat.completion", "created": int(time.time()),
        "model": body.get("model", "fake-chit-7b"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": len(user) // 4, "completion_tokens": len(text) // 4},
    })


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18999)
    ap.add_argument("--latency", type=float, default=0.3)
    a = ap.parse_args()
    STATE["latency"] = a.latency
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
