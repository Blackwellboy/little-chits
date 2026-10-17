"""The Brains dialog's Test: one real, tiny decision, and for whatever went wrong a plain cause and a fix.

The Test used to say reachable or not. A brain can be reachable and still decide nothing: its server refuses JSON
mode, the model spends the reply thinking, it sends no logprobs for the one-token choices, or it is too slow. So the
Test asks what the game asks (a one-chit scene through the normal prompt and parser, and a one-token choice with
logprobs, as the cascade does), on a client of its own, and `classify` turns what came back into findings: each one
a sentence, and a one-click fix where there is one (a patch for POST /api/brains).

A brain added without saying what its server takes (`detect`) starts with the plainest request, which every
OpenAI-compatible server takes; its first Test tries JSON mode and the thinking switch and keeps what works."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Dict, List, Optional

import httpx

from . import prompt as P
from .llm import BrainConfig, LLMBrain, ModelServerError
from .parse import ParseError, parse_plan

REPLY_CHARS = 200  # of the model's reply, shown as it came
CHOOSERS = ("choose", "cascade", "decide")  # prompt styles that pick by one token (decide: by decision model)


def _failure(e: Exception) -> Dict[str, str]:
    """Why a request got no usable answer: {"kind": "timeout" | "unreachable" | "http" | "error", "text"}."""
    if isinstance(e, httpx.TimeoutException):
        return {"kind": "timeout", "text": type(e).__name__}
    if isinstance(e, ModelServerError):
        return {"kind": "http", "text": str(e)}  # (the server's own words: llm.http_error_text)
    if isinstance(e, httpx.TransportError):
        return {"kind": "unreachable", "text": f"{type(e).__name__}: {e}"[:200]}
    return {"kind": "error", "text": f"{type(e).__name__}: {e}"[:200]}


async def _ask(brain: LLMBrain, msgs, kw: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.monotonic()
    try:
        res = await brain.chat(msgs, force=True, **kw)
    except Exception as e:
        return {"error": _failure(e), "latency_ms": (time.monotonic() - t0) * 1000}
    text = res["text"] or ""
    return {"text": text, "latency_ms": res["latency_ms"], "finish_reason": res.get("finish_reason"),
            "answered": bool(res.get("answered", text)), "top_logprobs": res.get("top_logprobs") or {},
            "thinking": bool(res.get("reasoned")) or "<think>" in text.lower()}


async def _ask_decide(brain: LLMBrain, world, a) -> Dict[str, Any]:
    """The Test's one-token choice for a decide brain: a real SystemOne vote on a drafted menu."""
    from .instinct import Instinct
    from .sysone import vote

    t0 = time.monotonic()
    try:
        opts = Instinct().options(world, a)
        state, criteria = P.decide_question(world, a, opts, None)
        v = await vote(brain, state, criteria)
    except Exception as e:
        return {"error": _failure(e), "latency_ms": (time.monotonic() - t0) * 1000}
    valid = P.LETTERS[:len(opts)]
    return {"text": v["choice"], "latency_ms": v["latency_ms"], "finish_reason": "stop",
            "answered": True, "top_logprobs": {}, "thinking": False,
            "logprobs": True, "letter": v["choice"] if v["choice"] in valid else ""}


async def observe(cfg: BrainConfig, client: Optional[httpx.AsyncClient] = None, seed: int = 1234) -> Dict[str, Any]:
    """Ask a server what the game would ask, and note what came back (the facts `classify` reads)."""
    from ..sim.world import World
    from ..tools.doctor import choice_letter, decision_request

    brain = LLMBrain(replace(cfg, enabled=True))
    brain.cooldown = False
    if client is not None:
        brain._client = client
    obs: Dict[str, Any] = {"url": cfg.base_url, "timeout": cfg.timeout, "models": None, "model": "", "error": None,
                           "plan": None, "choice": None}
    try:
        try:
            obs["models"] = await brain.list_models()
        except Exception as e:
            obs["error"] = _failure(e)
            return obs
        world = World("A", "Checkup", seed, "direct", 64, 2)
        a = next(iter(world.agents.values()))
        if cfg.prompt_style == "decide":
            # a decision model never writes plans: the Test asks only what the game asks it (the vote)
            c = obs["choice"] = await _ask_decide(brain, world, a)
            obs["model"] = brain.stats.resolved_model
            return obs
        msgs, kw, _ = decision_request(world, a, "compact" if cfg.prompt_style == "compact" else "full")
        p = obs["plan"] = await _ask(brain, msgs, kw)
        p["json_refused"] = bool(cfg.json_mode and not brain._json_ok)
        p["switch_refused"] = bool(cfg.disable_thinking and not brain._thinking_kw_ok)
        obs["model"] = brain.stats.resolved_model
        if "error" in p:
            if p["error"]["kind"] in ("timeout", "unreachable"):
                return obs  # (the choice would only wait as long again)
        else:
            try:
                plan = parse_plan(p["text"])
                p["parsed"] = {"goal": plan["goal"], "steps": [s.get("do", "?") for s in plan["steps"]]}
            except ParseError as e:
                p["parse_error"] = str(e)[:160]
        msgs, kw, letters = decision_request(world, a, "cascade" if cfg.prompt_style == "cascade" else "choose")
        c = obs["choice"] = await _ask(brain, msgs, kw)
        if "error" not in c:
            c["logprobs"] = bool(c["top_logprobs"])
            c["letter"] = choice_letter(c, letters)
        return obs
    finally:
        await brain.close()


def classify(obs: Dict[str, Any], cfg: BrainConfig) -> List[Dict[str, Any]]:
    """What a Test's observations mean: findings, each {"code", "level": "fail" | "warn" | "note", "text",
    "fix": {"label", "patch"} or None}. A "fail" stops the brain deciding; a "warn" costs it; a "note" is for
    knowing. The patch is the brain settings that fix it."""
    out: List[Dict[str, Any]] = []

    def add(code: str, level: str, text: str, label: str = "", **patch) -> None:
        if not any(f["code"] == code for f in out):
            out.append({"code": code, "level": level, "text": text, "fix": {"label": label, "patch": patch} if label else None})

    def failed(err: Dict[str, str], what: str) -> None:
        low = err["text"].lower()
        if err["kind"] == "timeout":
            add("timeout", "fail", f"No reply within {float(obs.get('timeout') or cfg.timeout):.0f} seconds. The model is too slow "
                "or too busy: use fewer chits, or give the server more parallel slots.")
        elif err["kind"] == "unreachable":
            add("unreachable", "fail", f"Nothing answered at {obs.get('url') or cfg.base_url}. Is the model server running, "
                "and is this its port?")
        elif err["kind"] == "http" and cfg.json_mode and ("response_format" in low or "json" in low):
            add("json_refused", "fail", f"The server refused JSON mode. It said: {err['text']}", "Turn JSON mode off", json_mode=False)
        elif err["kind"] == "http":
            add("http", "fail", f"The server refused {what}. It said: {err['text']}")
        else:
            add("error", "fail", f"{what.capitalize()} failed: {err['text']}")

    def thinking(level: str, text: str) -> None:
        if not cfg.disable_thinking:
            add("thinking", level, text, "Disable thinking", disable_thinking=True)
        elif level == "fail":
            more = min(4000, max(1200, 2 * int(cfg.max_tokens)))
            add("thinking", level, text + (" The server refused the switch that skips thinking." if p.get("switch_refused")
                                           else " It thinks even when asked not to.") + " More tokens leave room for the answer.",
                *((f"Raise max tokens to {more}",) if more > cfg.max_tokens else ()), **({"max_tokens": more} if more > cfg.max_tokens else {}))
        else:
            add("thinking", level, text + " It thinks even when asked not to.")

    p = obs.get("plan") or {}
    if obs.get("error"):
        failed(obs["error"], "the list of its models")
        return out
    if "error" in p:
        failed(p["error"], "the request")
    elif p:
        if p.get("json_refused") and cfg.json_mode:
            add("json_refused", "warn", "The server refused JSON mode. The request worked without it.", "Turn JSON mode off", json_mode=False)
        if p.get("thinking") and not p.get("answered"):
            thinking("warn" if p.get("parsed") else "fail", "The model spent its reply thinking and never gave an answer.")
        elif p.get("thinking"):
            thinking("warn", "The model thinks before it answers, which makes every decision slower.") if p.get("parsed") \
                else thinking("fail", "The reply was thinking, not a plan.")
        elif not (p.get("text") or "").strip():
            add("empty", "fail", "The model sent an empty reply."
                + (" It ran out of tokens." if p.get("finish_reason") == "length" else ""))
        elif not p.get("parsed"):
            add("unparsed", "fail", f"The reply was not a plan the game could read ({p.get('parse_error') or 'no plan in it'}). "
                "A shorter prompt or a lower temperature can help.",
                *(("Use the compact prompt",) if cfg.prompt_style == "full" else ()),
                **({"prompt_style": "compact"} if cfg.prompt_style == "full" else {}))
        if p.get("switch_refused") and cfg.disable_thinking and not p.get("thinking"):
            add("switch_refused", "note", "The server does not take the switch that skips thinking. This model answered "
                "without thinking anyway.", "Stop sending it", disable_thinking=False)
    c = obs.get("choice") or {}
    chooser = cfg.prompt_style in CHOOSERS
    to_full = ("Switch prompt style to full",) if chooser else ()
    patch = {"prompt_style": "full"} if chooser else {}
    if "error" in c:
        if not any(f["level"] == "fail" for f in out):  # (the same failure twice says nothing new)
            failed(c["error"], "the one-token choice")
    elif c:
        if c.get("thinking") and not c.get("letter"):
            thinking("fail" if chooser else "warn", "The model spent its one-token choice thinking.")
        if not c.get("letter"):
            # neither a letter the scores point to nor one in the reply: a choosing brain cannot decide
            add("no_letter", "fail" if chooser else "note",
                f"The one-token choice was not one of the option letters (it said \"{(c.get('text') or '').strip()[:20]}\")."
                + ("" if c.get("logprobs") else " The server sent no logprobs either."), *to_full, **patch)
        elif not c.get("logprobs"):
            # a valid letter with no logprobs still decides (the mind reads the reply itself: mind._choose); what is
            # lost is how sure the model was
            add("no_logprobs", "note", "The server sent no logprobs with the one-token choice. The letter it replied is "
                "used as it is; " + ("a cascade brain cannot tell when the model is unsure, so it writes its own plan only "
                                     "when the model asks to." if cfg.prompt_style == "cascade" else
                                     "the game cannot tell how sure the model was."))
    return out


def report(obs: Dict[str, Any], cfg: BrainConfig) -> Dict[str, Any]:
    """A Test's result for the Brains dialog: the reply, whether it parsed, the choice, the latency, the findings."""
    findings = classify(obs, cfg)
    p, c = obs.get("plan") or {}, obs.get("choice") or {}
    fails = [f["text"] for f in findings if f["level"] == "fail"]
    return {"ok": not fails, "models": obs.get("models") or [], "model": obs.get("model") or cfg.model,
            "reply": (p.get("text") or "")[:REPLY_CHARS] if "text" in p else None,
            "latency_ms": round(p["latency_ms"]) if "text" in p else None,
            "parsed": bool(p.get("parsed")), "plan": p.get("parsed") or None,
            "logprobs": c.get("logprobs") if "text" in c else None, "choice": c.get("letter") or "",
            "choice_latency_ms": round(c["latency_ms"]) if "text" in c else None,
            "findings": findings, "error": " ".join(fails), "detected": None}


async def diagnose(cfg: BrainConfig, client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    return report(await observe(cfg, client), cfg)


def _settled(obs: Dict[str, Any]) -> bool:
    """The server answered the plan request (well or badly): what it takes is known."""
    p = obs.get("plan") or {}
    return not obs.get("error") and bool(p) and (p.get("error") or {}).get("kind") not in ("timeout", "unreachable")


async def test_brain(mind, brain: LLMBrain, locked: bool = False, client_for=None) -> Dict[str, Any]:
    """The Test button. For a brain still marked `detect`, also find the settings its server takes: try JSON mode
    and the thinking switch, keep what was accepted (or neither, if only the plain request gives a plan), and save
    that. Never for a brain an experiment is using (`locked`): its settings are frozen."""
    cfg = brain.cfg
    client = client_for or (lambda: None)  # (tests hand in a transport; each observation closes its client)
    if not cfg.detect or locked:
        return await diagnose(cfg, client())
    tried = replace(cfg, json_mode=True, disable_thinking=True)
    obs = await observe(tried, client())
    p = obs.get("plan") or {}
    found = replace(tried, json_mode=not p.get("json_refused"), disable_thinking=not p.get("switch_refused"))
    if not obs.get("error") and not p.get("parsed") and (p.get("error") or {}).get("kind") not in ("timeout", "unreachable"):
        plain = replace(cfg, json_mode=False, disable_thinking=False)
        again = await observe(plain, client())
        if (again.get("plan") or {}).get("parsed"):
            obs, found = again, plain
    if not _settled(obs):
        return report(obs, cfg)  # (nothing learned: it stays to be detected)
    settings = {"json_mode": found.json_mode, "disable_thinking": found.disable_thinking}
    mind.upsert({"id": cfg.id, **settings, "detect": False})
    out = report(obs, replace(found, detect=False))
    out["findings"] = [f for f in out["findings"] if f["code"] not in ("json_refused", "switch_refused")]  # (settled)
    out["detected"] = settings
    return out
