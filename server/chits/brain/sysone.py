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


def _est_tokens(text: str) -> int:
    """Rough token count (chars/4): no tokenizer for the decision model on hand."""
    return max(1, len(text or "") // 4)


def _trim(text: str, max_tokens: int) -> str:
    """Shorten to ~max_tokens, keeping the head (identity) and the tail (body needs)."""
    if _est_tokens(text) <= max_tokens:
        return text
    head, _, rest = (text or "").partition("\n")
    keep_chars = max(120, max_tokens * 4 - len(head) - 8)
    if not rest:  # one long line: hard-cut it
        return head[:keep_chars] + "…"
    tail = rest[-keep_chars:]
    cut = tail.find("\n")
    tail = tail[cut + 1:] if cut != -1 and len(tail) > keep_chars * 0.7 else tail
    return head + "\n…\n" + tail


STATE_MAX = 280  # tokens: laya-class decision models run ctx 512; the question takes the rest
CRIT_MAX = 50  # tokens per option
TOTAL_MAX = 430  # tokens for state + criteria + instructions


def _fit(state: str, criteria: Dict[str, str], budget: int = TOTAL_MAX) -> tuple:
    """Trim criteria, then the state, until state + criteria + instructions fit the budget."""
    crit = {k: _trim(v, CRIT_MAX) for k, v in criteria.items()}
    used = sum(_est_tokens(v) for v in crit.values()) + 20  # instructions + framing
    state = _trim(state, max(120, min(STATE_MAX, budget - used)))
    if _est_tokens(state) + used > budget:  # many options: shrink the state to what is left
        state = _trim(state, max(120, budget - used))
    return state, crit


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
    if len(criteria) < 2:
        # the API needs 2–26 candidates: a single option is no contest, not a vote (the caller runs it unopposed
        # or falls back to the chat vote)
        raise SystemOneBadKey(f"only {len(criteria)} candidate(s): no contest to decide")
    body = {"model": model, "state": state,
            "questions": {question: {"type": "choice",
                                     "instructions": "Which plan should be followed?",
                                     "criteria": criteria}}}
    url, headers = endpoint(brain.cfg.base_url), brain.headers()
    await brain.sem.acquire(DECISION)
    try:
        t0 = time.monotonic()
        state, crit = _fit(state, criteria)
        body["state"], body["questions"][question]["criteria"] = state, crit
        r = await brain.client().post(url, headers=headers, content=json.dumps(body))
        t = r.text.lower()
        if r.status_code >= 400 and ("truncat" in t or "dropped" in t
                                     or ("token" in t and "limit" in t) or "too long" in t):
            # a 512-context decision model choking on a long scene: halve the budget once and retry.
            # (Ollama words it as tokens-vs-limit, Ollaya 422s STATE_TRUNCATED: "part of state was dropped")
            state, crit = _fit(state, criteria, budget=TOTAL_MAX // 2)
            body["state"], body["questions"][question]["criteria"] = state, crit
            t0 = time.monotonic()
            r = await brain.client().post(url, headers=headers, content=json.dumps(body))
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
