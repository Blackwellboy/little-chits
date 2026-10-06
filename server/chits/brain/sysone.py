"""SystemOne decision votes for "decide" brains (mind prompt_style "decide", brains.json only).

A decide brain drafts options with instinct like choose, but the pick goes to a
decision model over POST {root}/v1/systemone (Ollama 0.35+, TypeSafe Jev API)
instead of a one-token chat vote scored by logprobs. The answer carries real
probabilities at 1 output token.

Fallbacks (the game never stalls on a missing endpoint): a server without the
endpoint (404/405) raises SystemOneMissing; an answer naming no drafted option
raises SystemOneBadKey. The caller falls back to the one-token chat vote.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any, Dict, List

from .llm import DECISION, ModelServerError, http_error_text


def confidence(res: Dict[str, Any], scores: Dict[str, float], letter: str) -> Any:
    """The pick's probability: the decision model's own, else the logprob score, else unknown."""
    p = (res.get("probabilities") or {}).get(letter)
    if p is not None:
        return round(float(p), 2)
    return round(math.exp(scores[letter]), 2) if letter in scores else None


class SystemOneMissing(RuntimeError):
    """The server has no decision endpoint (not Ollama 0.35+, or decision models off)."""


class SystemOneBadKey(RuntimeError):
    """The decision model answered with an option that was never drafted."""


def endpoint(base_url: str) -> str:
    """The SystemOne URL beside a chat base URL (…/v1 or …/chat/completions)."""
    root = (base_url or "").strip().rstrip("/")
    if root.endswith("/chat/completions"):
        root = root[: -len("/chat/completions")]
    elif root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root + "/v1/systemone"


async def vote(brain, state: str, criteria: Dict[str, str], question: str = "pick") -> Dict[str, Any]:
    """Ask the decision model to pick: {choice, probabilities, confidence, latency_ms, ...}.

    Raises SystemOneMissing (no endpoint: fall back), SystemOneBadKey (unknown
    option: fall back), ModelServerError (a real failure: the decision fails).
    """
    model = brain.cfg.model or brain.stats.resolved_model
    if not model:
        model = await brain.resolve_model()
    body = {"model": model, "state": state,
            "questions": {question: {"type": "choice",
                                     "instructions": "Which plan should be followed?",
                                     "criteria": criteria}}}
    await brain.sem.acquire(DECISION)
    try:
        t0 = time.monotonic()
        r = await brain.client().post(endpoint(brain.cfg.base_url), headers=brain.headers(),
                                      content=json.dumps(body))
    finally:
        brain.sem.release()
    ms = (time.monotonic() - t0) * 1000
    if r.status_code in (404, 405):
        raise SystemOneMissing(f"no decision endpoint at {endpoint(brain.cfg.base_url)} "
                               f"(HTTP {r.status_code}): fall back to the one-token vote")
    if r.status_code >= 400:
        raise ModelServerError(http_error_text(r))
    data = r.json()
    ans = ((data.get("answers") or {}).get(question) or {})
    choice = str(ans.get("choice") or "")
    if ans.get("type", "choice") != "choice" or choice not in criteria:
        raise SystemOneBadKey(f"decision answer {choice!r} names no drafted option: fall back")
    probs = {k: float((ans.get("probabilities") or {}).get(k, 0.0)) for k in criteria}
    usage = data.get("usage") or {}
    brain.stats.record_latency(ms)
    brain.latencies.append(ms)
    brain.stats.tokens_out += int(usage.get("output_tokens") or 1)
    brain.stats.tokens_in += int(usage.get("input_tokens") or 0)
    return {"text": choice, "latency_ms": ms, "tokens_in": usage.get("input_tokens"),
            "tokens_out": int(usage.get("output_tokens") or 1), "top_logprobs": {}, "queue_ms": 0,
            "finish_reason": "stop", "answered": True, "choice": choice,
            "probabilities": probs, "confidence": ans.get("confidence")}


async def decide_letters(brain, state: str, options: List[str], question: str = "pick") -> Dict[str, Any]:
    """A letter-vote (elections, chief projects, trade offers) through the decision model: the vote dict,
    whose text is the chosen letter. The labels name each letter; a missing one falls back to the letter
    itself. Raises SystemOneMissing/BadKey: the caller falls back to the one-token chat vote."""
    from . import prompt as P  # local: prompt never imports sysone

    criteria = {P.LETTERS[i]: (o or P.LETTERS[i]) for i, o in enumerate(options)}
    v = await vote(brain, state, criteria, question)
    if v["choice"] not in P.LETTERS[:len(options)]:
        raise SystemOneBadKey(f"decision answer {v['choice']!r} names no drafted option: fall back")
    return v
