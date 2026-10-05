"""A scripted stand-in model for the harness: deterministic, seeded, no GPU and no network.

It answers the game's own requests the way a small model does: a letter for a choice (with logprobs, so the cascade's
confidence gate and escalation run), a JSON plan for a full request, lessons for a weekly reflection. It reads only the
prompt, as a model does. At a set rate it answers badly, in the ways live models have: an invalid letter, an item that
doesn't exist, ``"what": null``, a step that can't run here, a verb that doesn't exist, cut-off JSON and prose with no
JSON at all.

It plugs in below the game's model client (brain/llm.py ``LLMBrain.chat``), as an ``httpx.MockTransport``: the request
body, the reply parsing, the priority gate and the brain's counters all run as they do against a real server. A reply
takes a set number of world ticks (``TickClock``), not wall time, so a run is the same on every machine.

    model = ScriptedModel(seed=42, bad_rate=0.15)
    clock = TickClock()
    brain._client = httpx.AsyncClient(transport=httpx.MockTransport(ScriptedTransport(model, clock)))
"""

from __future__ import annotations

import asyncio
import hashlib
import heapq
import json
import math
import random
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

BAD_KINDS = ("bad_letter", "none_what", "unreal_item", "cant_run", "unknown_verb", "truncated", "prose")
LETTER_KINDS = ("bad_letter",)  # what a one-letter answer can get wrong
PLAN_KINDS = tuple(k for k in BAD_KINDS if k not in LETTER_KINDS)
UNREAL = ("moonstone", "sky glass", "dragon scale", "starlight")  # items no world has
FOOD_WORDS = ("berries", "fish", "grain", "bread", "meat", "cooked")
OPTION = re.compile(r"^([A-I])\) (.*)$", re.M)


class ScriptedModel:
    """The policy. ``bad_rate`` is the share of answers that go wrong; ``bad_kinds`` which ways (default: all).
    Every answer is drawn from a generator seeded by the run's seed and the exact request, so the same request in the
    same run gets the same answer."""

    def __init__(self, seed: int = 0, bad_rate: float = 0.15, bad_kinds: Optional[Tuple[str, ...]] = None,
                 choice_ticks: int = 1, plan_ticks: int = 8):
        unknown = set(bad_kinds or ()) - set(BAD_KINDS)
        if unknown:
            raise ValueError(f"unknown bad kinds {sorted(unknown)}; known: {', '.join(BAD_KINDS)}")
        self.seed, self.bad_rate = seed, bad_rate
        self.bad_kinds = tuple(bad_kinds) if bad_kinds else BAD_KINDS
        self.choice_ticks, self.plan_ticks = choice_ticks, plan_ticks
        self.calls = 0
        self.planted: Counter = Counter()  # bad kind -> answers that carried it
        self.answered: Counter = Counter()  # request kind -> answers
        self.texts: Dict[str, str] = {}  # sha256(text)[:16] -> the reply text (the decision records keep only the hash)

    # ------------------------------------------------------------------ entry point
    def respond(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """An OpenAI chat-completion response for one request body."""
        self.calls += 1
        msgs = body.get("messages") or []
        rng = random.Random(f"{self.seed}|{self.calls}|{hashlib.sha256(json.dumps(msgs, sort_keys=True).encode()).hexdigest()}")
        system = msgs[0]["content"] if msgs else ""
        user = msgs[-1]["content"] if msgs else ""
        if body.get("max_tokens") == 1:
            self.answered["letter"] += 1
            return self._letter(body, user, rng)
        if "reflecting" in system:
            self.answered["reflection"] += 1
            text = self._reflection(user, rng)
        elif "Reply exactly" in user:  # (the Test button)
            text = '{"ok": true, "word": "chit"}'
        else:
            self.answered["plan"] += 1
            text = self._plan(user, rng)
        self.texts[hashlib.sha256(text.encode()).hexdigest()[:16]] = text
        return _completion(text, "stop", len(user) // 4, max(1, len(text) // 4))

    def _bad(self, rng: random.Random, kinds: Tuple[str, ...]) -> Optional[str]:
        allowed = [k for k in self.bad_kinds if k in kinds]
        if allowed and rng.random() < self.bad_rate:
            k = rng.choice(allowed)
            self.planted[k] += 1
            return k
        return None

    # ------------------------------------------------------------------ one letter
    def _letter(self, body: Dict[str, Any], user: str, rng: random.Random) -> Dict[str, Any]:
        opts = OPTION.findall(user)
        if self._bad(rng, LETTER_KINDS) or not opts:
            letter, top = rng.choice(["Z", "The", "1"]), [("The", -0.4), ("Z", -1.5), ("1", -2.5)]
        else:
            letters = [l for l, _ in opts]
            own = [l for l, t in opts if t.startswith("something else")]
            real = [l for l in letters if l not in own]
            starving = re.search(r"\b(starving|hungry)\b", user.split("YOUR OPTIONS:")[0]) is not None
            eat = [l for l, t in opts if t.startswith("eat") or "eat" in t.split(":")[0]]
            if starving and eat:
                letter = eat[0]
            elif own and rng.random() < 0.12:
                letter = own[0]
            else:
                letter = rng.choice(real or letters)
            p = rng.choice([0.92, 0.8, 0.66, 0.45, 0.3])  # below the cascade's 0.5 it escalates to a full plan
            rest = [l for l in letters if l != letter]
            top = [(letter, math.log(p))] + [(l, math.log((1 - p) / max(1, len(rest)))) for l in rest]
        choice: Dict[str, Any] = {"index": 0, "message": {"role": "assistant", "content": letter}, "finish_reason": "length"}
        if body.get("logprobs"):
            choice["logprobs"] = {"content": [{"token": letter, "logprob": top[0][1],
                                               "top_logprobs": [{"token": t, "logprob": lp} for t, lp in top]}]}
        return {"id": f"scripted-{self.calls}", "object": "chat.completion", "model": "scripted", "choices": [choice],
                "usage": {"prompt_tokens": len(user) // 4, "completion_tokens": 1}}

    # ------------------------------------------------------------------ a full plan
    def _plan(self, user: str, rng: random.Random) -> str:
        bad = self._bad(rng, PLAN_KINDS)
        if bad == "prose":
            return "I think I will go and look for some berries, maybe, or perhaps some wood."
        plan = self._good_plan(scene(user), rng)
        steps = plan["plan"]
        if bad == "none_what":
            steps.insert(0, {"do": "gather", "what": None, "qty": 3})
        elif bad == "unreal_item":
            thing = rng.choice(UNREAL)
            steps.insert(0, rng.choice([{"do": "experiment", "with": [thing, "stone"]},
                                        {"do": "gather", "what": thing, "qty": 2},
                                        {"do": "craft", "what": thing}]))
        elif bad == "cant_run":
            steps.insert(0, rng.choice([{"do": "take", "what": "iron", "qty": 3},
                                        {"do": "store", "what": "iron"},
                                        {"do": "help", "site": "s9999"},
                                        {"do": "work", "at": "factory"}]))
        elif bad == "unknown_verb":
            steps.insert(rng.randrange(len(steps) + 1), {"do": "levitate", "to": "the moon"})
        text = json.dumps(plan)
        if bad == "truncated":
            text = text[: max(40, int(len(text) * 0.7))]  # a reply that ran out of tokens mid-plan
        return text

    def _good_plan(self, s: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
        carrying, near = s["carrying"], s["near"]
        food_held = [k for k in carrying if any(f in k for f in FOOD_WORDS)]
        failed = s["failed"] or ""

        def plan(goal: str, thought: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
            return {"thought": thought, "goal": goal, "plan": steps}

        if s["hunger"] < 40:
            if food_held:
                return plan("eat", "My belly aches.", [{"do": "eat", "what": food_held[0]}])
            if "berries" in near and "berries" not in failed:
                return plan("eat", "Berries first.", [{"do": "gather", "what": "berries", "qty": 4}, {"do": "eat"}])
            return plan("eat", "There is food in the stores.", [{"do": "take", "what": "berries", "qty": 3}, {"do": "eat"}])
        r = rng.random()
        if s["no_home"] and "hut" in s["designs"] and r < 0.5:
            return plan("build a hut", "I need a roof.", [{"do": "gather", "what": "wood", "qty": 8},
                                                          {"do": "gather", "what": "plant fiber", "qty": 4},
                                                          {"do": "build", "what": "hut"}])
        if s["sites"] and r < 0.25:
            return plan("help build", "Many hands.", [{"do": "help", "site": rng.choice(s["sites"])}])
        if s["untried"] and r < 0.45:
            combo = rng.choice(s["untried"])
            items = [x.strip() for x in combo.split(" at the ")[0].split("+")]
            at = combo.split(" at the ")[1].strip() if " at the " in combo else None
            pre = [{"do": "gather", "what": x, "qty": 1} for x in dict.fromkeys(items) if x not in carrying and x in near]
            step = {"do": "experiment", "with": items}
            if at:
                step["at"] = at
            return plan("try something new", "What if these went together?", pre[:2] + [step])
        if s["recipes"] and r < 0.6:
            what = rng.choice(s["recipes"])
            return plan(f"make {what}", "A useful thing to have.", [{"do": "craft", "what": what, "qty": 1}])
        if r < 0.7:
            return plan("explore", "What lies beyond?", [{"do": "explore", "dir": rng.choice(["N", "S", "E", "W"])}])
        pick = [x for x in ("wood", "stone", "plant fiber", "clay", "berries") if x in near] or ["wood"]
        what = rng.choice(pick)
        return plan(f"collect {what}", f"We'll always need {what}.",
                    [{"do": "gather", "what": what, "qty": 6}, {"do": "store", "what": "all"}])

    # ------------------------------------------------------------------ reflection
    def _reflection(self, user: str, rng: random.Random) -> str:
        if self._bad(rng, ("prose", "truncated")):
            return "Lessons: be careful, and"
        mems = [int(m) for m in re.findall(r"\[m(\d+)\]", user)]
        cite = mems[-2:] if mems else []
        return json.dumps({"lessons": [{"text": "Keep food in the stores before the cold comes.", "from": cite}],
                           "ambition": "Make something nobody has made before"})


def scene(user: str) -> Dict[str, Any]:
    """What the policy reads from a full plan request's scene (brain/prompt.py scene())."""
    def grab(rx: str) -> str:
        m = re.search(rx, user)
        return m.group(1) if m else ""

    hunger = grab(r"Hunger (\d+)/100")
    carrying = [re.sub(r"^\d+ ", "", x).strip() for x in grab(r"Carrying \(\d+/\d+\): (.*?)\.\n").split(", ")
                if x and x != "nothing"]
    near = [re.sub(r" \d+ tiles? .*$", "", x).strip() for x in grab(r"- Resources: (.*)").split("; ") if x]
    recipes = [x.split("->")[1].split("(")[0].strip() for x in grab(r"YOU KNOW HOW TO MAKE: (.*)").split("; ") if "->" in x]
    designs = [x.split("(")[0].strip() for x in grab(r"YOU KNOW HOW TO BUILD: (.*)").split("); ") if x]
    untried = [x.strip() for x in grab(r"you have never tried: (.*?)\.?\n").split("; ") if x.strip()]
    return {"hunger": int(hunger) if hunger else 60, "carrying": carrying, "near": near, "recipes": recipes,
            "designs": designs, "untried": untried, "no_home": "You have no home yet" in user,
            "sites": re.findall(r"CONSTRUCTION SITE (\S+):", user), "failed": grab(r'YOUR PLAN FAILED: "([^"]*)"')}


def _completion(text: str, finish: str, tin: int, tout: int) -> Dict[str, Any]:
    return {"id": "scripted", "object": "chat.completion", "model": "scripted",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": tin, "completion_tokens": tout}}


class TickClock:
    """World time for replies: ``wait(n)`` resolves once ``advance()`` has been called n times."""

    def __init__(self) -> None:
        self.tick = 0
        self._wait: List[tuple] = []
        self._seq = 0

    def wait(self, n: int) -> "asyncio.Future":
        fut = asyncio.get_running_loop().create_future()
        if n <= 0:
            fut.set_result(None)
            return fut
        self._seq += 1
        heapq.heappush(self._wait, (self.tick + n, self._seq, fut))
        return fut

    def advance(self) -> None:
        self.tick += 1
        while self._wait and self._wait[0][0] <= self.tick:
            _, _, fut = heapq.heappop(self._wait)
            if not fut.done():
                fut.set_result(None)

    def waiting(self) -> int:
        return sum(1 for _, _, f in self._wait if not f.done())


class ScriptedTransport:
    """The ``httpx.MockTransport`` handler: /models lists one model; /chat/completions answers after the model's
    reply time in ticks (a one-letter answer is quicker than a written plan)."""

    def __init__(self, model: ScriptedModel, clock: TickClock):
        self.model, self.clock = model, clock
        self.received: List[tuple] = []  # (clock tick, "letter" | "text") for each request, in arrival order

    async def __call__(self, request):
        import httpx

        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"object": "list", "data": [{"id": "scripted", "object": "model"}]})
        body = json.loads(request.content or b"{}")
        letter = body.get("max_tokens") == 1
        self.received.append((self.clock.tick, "letter" if letter else "text"))
        await self.clock.wait(self.model.choice_ticks if letter else self.model.plan_ticks)
        return httpx.Response(200, json=self.model.respond(body))
