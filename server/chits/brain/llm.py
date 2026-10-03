"""OpenAI-compatible model client. Works with llama.cpp, vLLM, Ollama, LM Studio,
SGLang, TabbyAPI, OpenRouter, OpenAI — anything that serves /v1/chat/completions.
"""

from __future__ import annotations

import asyncio
import hashlib
import heapq
from collections import deque
import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import httpx


def request_seed(base: int, messages: Any) -> int:
    """A sampling seed from a run's seed and the exact prompt (research plan item 43): the same question in the same
    run samples the same way on a server that honours `seed` (llama.cpp and vLLM do), so a difference between two
    arms is less often sampling luck. (It doesn't make a GPU bitwise deterministic under batching.)"""
    blob = json.dumps([int(base), messages], sort_keys=True, ensure_ascii=False, default=str)
    return int(hashlib.sha256(blob.encode()).hexdigest()[:8], 16) % 2**31


@dataclass
class BrainConfig:
    id: str
    label: str = ""
    base_url: str = ""
    model: str = ""  # empty = first model the server lists
    api_key: str = ""  # literal key, or "env:VAR_NAME"
    # Tuned for 8-30B instruct models driving ~18 chits: enough parallelism to keep a GPU busy,
    # warm enough to vary plans, room for a plan plus a short thought without truncation.
    max_concurrency: int = 6
    timeout: float = 90.0
    temperature: float = 0.7
    max_tokens: int = 600
    json_mode: bool = True  # send response_format=json_object (auto-disabled if the server rejects it)
    disable_thinking: bool = True  # ask Qwen3-style models to skip <think> (chat_template_kwargs)
    extra_body: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    prompt_style: str = "full"  # "full", "compact", "choose" (pick a drafted plan) or "cascade" (choose, escalating)
    escalate_below: float = 0.5  # cascade: a choice less sure than this (or "my own idea") gets a full, written plan
    escalate_share: float = 0.3  # cascade: at most this share of recent decisions become full plans (qwen3.8-s asked for
    #                              its own idea 3 times in 4, and a full plan on top of every choice swamped the 5090)
    focus: bool = True  # play games: plans that are only eating, sleeping, resting, sheltering or hauling are left to
    #                     instinct, so the model's time goes to the decisions that matter (never in an experiment)

    def key(self) -> str:
        k = self.api_key or ""
        if k.startswith("env:"):
            return os.environ.get(k[4:], "")
        return k

    def public(self) -> Dict[str, Any]:
        d = asdict(self)
        d["api_key"] = ("env:" + self.api_key[4:]) if self.api_key.startswith("env:") else ("•••" if self.api_key else "")
        return d


def _merge(body: Dict[str, Any], more: Dict[str, Any]) -> None:
    """Add settings to a request body. A dict merges into the one already there (a user's chat_template_kwargs adds to
    ours, so enable_thinking stays off unless it sets that itself); anything else replaces."""
    for k, v in more.items():
        if isinstance(v, dict) and isinstance(body.get(k), dict):
            body[k] = {**body[k], **v}
        else:
            body[k] = v


@dataclass
class BrainStats:
    requests: int = 0
    ok: int = 0
    failed: int = 0
    parse_failed: int = 0
    cut_off: int = 0  # replies whose reasoning ran out of tokens before any answer (not used as a plan)
    in_flight: int = 0
    queued: int = 0
    latency_ms_avg: float = 0.0
    tokens_out: int = 0
    tokens_in: int = 0
    tok_per_s: float = 0.0
    last_error: str = ""
    last_error_at: float = 0.0  # (when it happened)
    last_ok: float = 0.0
    consecutive_fail: int = 0
    ok_streak: int = 0  # replies in a row since the last failure: RECOVERED_AFTER of them clear last_error (issue #62)
    repaired: int = 0  # replies that only parsed after repairing the JSON
    retries: int = 0   # replies that needed a second "JSON only, please" request
    skipped: int = 0   # queued requests not sent because the server went down while they waited
    resolved_model: str = ""

    def record_latency(self, ms: float) -> None:
        a = 0.2 if self.ok > 1 else 1.0
        self.latency_ms_avg = self.latency_ms_avg * (1 - a) + ms * a


RECOVERED_AFTER = 10  # good replies in a row after which a brain's last error is history, not news (issue #62)
FEATURE_RETRIES = 3  # optional request features (JSON mode, thinking switch, logprobs) a server may reject in turn


def http_error_text(r) -> str:
    """A model server's error as it said it: the status and its own message. (httpx's text named only the status
    and linked a general page about it: the server's actual complaint was lost, issues #61 and #65.)"""
    body = (r.text or "").strip()
    try:
        j = r.json()
        err = j.get("error", j) if isinstance(j, dict) else j
        body = (err.get("message") or err.get("detail") or body) if isinstance(err, dict) else str(err)
    except ValueError:
        pass
    return f"HTTP {r.status_code}: {' '.join(str(body).split())[:200] or r.reason_phrase}"


class ModelServerError(RuntimeError):
    """A model server answered with an error status (the message is the server's own)."""


class ModelCoolingDown(RuntimeError):
    """A queued request given up without being sent: its brain is backing off after repeated failures."""


class PriorityGate:
    """A semaphore whose waiters are served by priority, then by arrival (issue #3): one-token decisions (a chief's
    choice, a cascade pick) ahead of full plans and reflections. On a live run with one 3090 for 90 chits, ~105
    requests waited here and 14 of 18 chief answers arrived after the question had expired."""

    def __init__(self, n: int):
        self._free = n
        self._wait: List[Any] = []
        self._seq = 0

    async def acquire(self, priority: int = 1) -> None:
        if self._free > 0 and not self._wait:
            self._free -= 1
            return
        fut = asyncio.get_running_loop().create_future()
        self._seq += 1
        heapq.heappush(self._wait, (priority, self._seq, fut))
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self.release()  # granted just as it was cancelled: pass the slot on
            raise

    def release(self) -> None:
        while self._wait:
            _, _, fut = heapq.heappop(self._wait)
            if not fut.done():  # (a cancelled waiter is skipped)
                fut.set_result(True)
                return
        self._free += 1

    def waiting(self) -> int:
        return sum(1 for _, _, f in self._wait if not f.done())


DECISION, PLAN = 0, 1  # priorities: one-token decisions first


class LLMBrain:
    def __init__(self, cfg: BrainConfig):
        self.cfg = cfg
        self.stats = BrainStats()
        self.latencies: deque = deque(maxlen=300)
        self.done_log: deque = deque(maxlen=2000)  # (finish time, tokens out) for real throughput
        self.sem = PriorityGate(max(1, cfg.max_concurrency))
        self._client: Optional[httpx.AsyncClient] = None
        self._json_ok = cfg.json_mode
        self._thinking_kw_ok = True
        self._logprobs_ok = True
        self.cooldown_until = 0.0

    @property
    def id(self) -> str:
        return self.cfg.id

    @property
    def label(self) -> str:
        return self.cfg.label or self.stats.resolved_model or self.cfg.model or self.cfg.id

    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.cfg.timeout, connect=6.0))
        return self._client

    def throughput(self, window: float = 60.0) -> float:
        """Tokens per second the server actually delivered over the last minute, across all parallel requests.
        (Per-request tok/s includes time spent queued on the server, so it looks slow when requests wait.)"""
        now = time.monotonic()
        toks = sum(n for t, n in self.done_log if now - t <= window)
        first = next((t for t, _ in self.done_log if now - t <= window), None)
        span = max(10.0, min(window, now - first)) if first else window
        return toks / span

    def healthy(self) -> bool:
        return self.cfg.enabled and time.monotonic() >= self.cooldown_until

    def headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        k = self.cfg.key()
        if k:
            h["Authorization"] = f"Bearer {k}"
        return h

    async def list_models(self) -> List[str]:
        url = self.cfg.base_url.rstrip("/") + "/models"
        r = await self.client().get(url, headers=self.headers(), timeout=8.0)
        if r.status_code >= 400:
            raise ModelServerError(http_error_text(r))
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        out = []
        for m in items or []:
            out.append(m.get("id") if isinstance(m, dict) else str(m))
        if isinstance(data, dict) and not out and data.get("models"):  # ollama native shape
            out = [m.get("name") for m in data["models"]]
        return [m for m in out if m]

    async def resolve_model(self) -> str:
        if self.cfg.model:
            self.stats.resolved_model = self.cfg.model
            return self.cfg.model
        if self.stats.resolved_model:
            return self.stats.resolved_model
        models = await self.list_models()
        if not models:
            raise RuntimeError("server lists no models")
        self.stats.resolved_model = models[0]
        return models[0]

    async def chat(self, messages: Any, *, max_tokens: Optional[int] = None,
                   temperature: Optional[float] = None, extra: Optional[Dict[str, Any]] = None,
                   json_reply: bool = True, priority: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
        """Returns {"text", "latency_ms", "tokens_in", "tokens_out"}; raises on transport/HTTP failure.
        `priority`: DECISION or PLAN; by default a one-token request is a DECISION and goes ahead of the queue.
        `messages` may be a function that builds them: it's called once a slot is free, so a request that queued
        for seconds still describes the world as it is when it's sent."""
        queued_at = time.monotonic()
        self.stats.queued += 1
        try:
            await self.sem.acquire(priority if priority is not None else (DECISION if max_tokens == 1 else PLAN))
        finally:
            self.stats.queued -= 1
        queue_ms = (time.monotonic() - queued_at) * 1000
        try:
            if not force and not self.healthy():
                # the server went down while this waited for a slot: don't send it into the same 90 s hang (live,
                # with the 3090's server gone, 111 queued requests each waited their turn to time out)
                self.stats.skipped += 1
                raise ModelCoolingDown(f"{self.label} is switched off" if not self.cfg.enabled else
                                       f"{self.label} is cooling down after {self.stats.consecutive_fail} failures in a row")
            if callable(messages):
                messages = messages()
            tape = getattr(self, "tape", None)  # a BrainTape (brain/tape.py): record every reply, or replay them
            key = None
            if tape is not None:
                from .tape import request_key

                key = request_key(self.cfg.id, messages, max_tokens, temperature, extra, json_reply)
                if tape.mode == "replay":
                    self.stats.requests += 1
                    tape.last_messages = messages
                    try:
                        reply = tape.play(key)  # raises TapeMiss when the run has diverged
                    except Exception as e:  # (a recorded failure fails again, and counts the same way)
                        self.stats.failed += 1
                        self.stats.consecutive_fail += 1
                        self.stats.last_error = f"{type(e).__name__}: {str(e)[:200]}"
                        raise
                    self.stats.consecutive_fail = 0
                    return reply
            self.stats.in_flight += 1
            self.stats.requests += 1
            t0 = time.monotonic()
            try:
                model = await self.resolve_model()
                body: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": self.cfg.temperature if temperature is None else temperature,
                    "max_tokens": max_tokens or self.cfg.max_tokens,
                    "stream": False,
                }
                if self._json_ok and json_reply:
                    body["response_format"] = {"type": "json_object"}
                if self.cfg.disable_thinking and self._thinking_kw_ok:
                    body["chat_template_kwargs"] = {"enable_thinking": False}
                _merge(body, self.cfg.extra_body or {})
                _merge(body, extra or {})
                if getattr(self, "seed_base", None) is not None and "seed" not in body:
                    body["seed"] = request_seed(self.seed_base, messages)
                if not self._logprobs_ok:
                    body.pop("logprobs", None)
                    body.pop("top_logprobs", None)
                url = self.cfg.base_url.rstrip("/") + "/chat/completions"
                r = await self.client().post(url, headers=self.headers(), content=json.dumps(body))
                # some servers reject an optional feature (JSON mode, the thinking switch, logprobs): drop what the
                # server names, or all of them, and try again. One at a time, and on 422 too: LM Studio refused
                # json_object mode, and a brain sat at 95 requests with none answered (issue #61)
                for _ in range(FEATURE_RETRIES):
                    optional = [k for k in ("response_format", "chat_template_kwargs", "logprobs") if k in body]
                    if r.status_code not in (400, 422) or not optional:
                        break
                    txt = r.text.lower()
                    named = [k for k, words in (("response_format", ("response_format", "json")),
                                                ("chat_template_kwargs", ("chat_template", "kwargs", "extra")),
                                                ("logprobs", ("logprobs",)))
                             if k in body and any(w in txt for w in words)]
                    for k in named or optional:
                        if k == "response_format":
                            self._json_ok = False
                        elif k == "chat_template_kwargs":
                            self._thinking_kw_ok = False
                        else:
                            self._logprobs_ok = False
                            body.pop("top_logprobs", None)
                        body.pop(k, None)
                    r = await self.client().post(url, headers=self.headers(), content=json.dumps(body))
                if r.status_code >= 400:
                    raise ModelServerError(http_error_text(r))
                data = r.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                text = msg.get("content") or choice.get("text") or ""
                if not text and msg.get("reasoning_content"):
                    if choice.get("finish_reason") == "length":
                        # thinking ran out of tokens before any answer: the cut-off reasoning is not a plan
                        self.stats.cut_off += 1
                    else:
                        text = msg["reasoning_content"]
                usage = data.get("usage") or {}
                ms = (time.monotonic() - t0) * 1000
                tout = int(usage.get("completion_tokens") or max(1, len(text) // 4))
                self.stats.tokens_out += tout
                self.stats.tokens_in += int(usage.get("prompt_tokens") or 0)
                self.stats.record_latency(ms)
                self.latencies.append(ms)
                self.done_log.append((time.monotonic(), tout))
                if ms > 0:
                    tps = tout / (ms / 1000)
                    self.stats.tok_per_s = tps if self.stats.tok_per_s == 0 else self.stats.tok_per_s * 0.8 + tps * 0.2
                self.stats.consecutive_fail = 0
                self.stats.last_ok = time.time()
                self.stats.ok_streak += 1
                if self.stats.ok_streak >= RECOVERED_AFTER:
                    self.stats.last_error = ""
                first = ((choice.get("logprobs") or {}).get("content") or [{}])[0] or {}
                top = {t.get("token", ""): t.get("logprob", -99.0) for t in (first.get("top_logprobs") or [])}
                reply = {"text": text, "latency_ms": ms, "tokens_in": usage.get("prompt_tokens"), "tokens_out": tout,
                         "top_logprobs": top, "queue_ms": queue_ms, "finish_reason": choice.get("finish_reason")}
                if tape is not None:
                    tape.record(key, self.cfg.id, reply, messages)
                return reply
            except Exception as e:
                self.stats.failed += 1
                self.stats.consecutive_fail += 1
                self.stats.ok_streak = 0
                self.stats.last_error = str(e)[:200] if isinstance(e, ModelServerError) else f"{type(e).__name__}: {str(e)[:200]}"
                self.stats.last_error_at = time.time()
                if tape is not None and tape.mode == "record":
                    tape.record_error(key, self.cfg.id, self.stats.last_error, messages)
                if self.stats.consecutive_fail >= 3 and getattr(self, "cooldown", True):
                    # back off so a dead server doesn't stall everyone; instinct covers meanwhile
                    self.cooldown_until = time.monotonic() + min(60, 5 * self.stats.consecutive_fail)
                raise
            finally:
                self.stats.in_flight -= 1
        finally:
            self.sem.release()

    async def test(self) -> Dict[str, Any]:
        t0 = time.monotonic()
        try:
            models = await self.list_models()
        except Exception as e:
            return {"ok": False, "error": f"could not list models: {type(e).__name__}: {e}"[:300]}
        try:
            res = await self.chat([
                {"role": "system", "content": "Reply with JSON only."},
                {"role": "user", "content": 'Reply exactly: {"ok": true, "word": "chit"}'},
            ], max_tokens=40, temperature=0.0, force=True)  # (the Test button asks even a switched-off or cooling
            # brain: that's how you find out its server is back, Codex #28)
        except Exception as e:
            return {"ok": False, "models": models, "error": f"{type(e).__name__}: {e}"[:300]}
        return {"ok": True, "models": models, "model": self.stats.resolved_model, "reply": res["text"][:200],
                "latency_ms": round((time.monotonic() - t0) * 1000)}

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()


COMMON_PORTS = [18090, 18080, 8080, 8000, 8001, 5000, 5001, 11434, 1234, 30000, 7860, 18999]


def _candidates(base_url: str) -> List[str]:
    u = (base_url or "").strip().rstrip("/")
    if u and "://" not in u:
        u = "http://" + u
    for suffix in ("/chat/completions", "/models"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
    out = [u]
    if not u.endswith("/v1"):
        out.append(u + "/v1")
    else:
        out.append(u[:-3])
    return [c for c in out if c]


async def probe_endpoint(base_url: str, api_key: str = "", timeout: float = 4.0) -> Dict[str, Any]:
    """Find the working OpenAI-compatible base URL near what the user typed, list its models and
    suggest a parallel-request count (llama.cpp reports its slots on /props)."""
    errors = []
    for cand in _candidates(base_url):
        b = LLMBrain(BrainConfig(id="probe", base_url=cand, api_key=api_key or ""))
        try:
            models = await asyncio.wait_for(b.list_models(), timeout)
            if not models:
                errors.append(f"{cand}: no models listed")
                continue
            slots = None
            try:
                root = cand[:-3] if cand.endswith("/v1") else cand
                r = await b.client().get(root + "/props", timeout=2.0)
                if r.status_code == 200:
                    slots = (r.json() or {}).get("total_slots")
            except Exception:
                pass
            conc = int(slots) if isinstance(slots, int) and slots > 0 else 6
            return {"ok": True, "base_url": cand, "models": models, "slots": slots,
                    "suggested": {"max_concurrency": max(1, min(conc, 16)), "temperature": 0.7, "max_tokens": 600}}
        except Exception as e:
            errors.append(f"{cand}: {type(e).__name__}: {e}"[:200])
        finally:
            await b.close()
    return {"ok": False, "error": " | ".join(errors)[:600]}


# Where model servers usually live: llama.cpp/vLLM/SGLang/TGI/LM Studio/Ollama/Kobold/text-gen defaults, plus the
# whole 18000-19999 block people use for GPU-per-port setups. Only ports that accept a TCP connection get probed.
SCAN_RANGES = [(1234, 1240), (5000, 5010), (5001, 5001), (7860, 7870), (8000, 8200), (8888, 8890), (9000, 9010),
               (11434, 11440), (18000, 19999), (20000, 20010), (30000, 30010)]


def _parse_ports(spec: str) -> List[int]:
    out: List[int] = []
    for part in spec.replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                out += range(int(a), int(b) + 1)
        elif part.isdigit():
            out.append(int(part))
    return out


async def _open_ports(host: str, ports: List[int], timeout: float = 0.4, limit: int = 256) -> List[int]:
    sem = asyncio.Semaphore(limit)

    async def one(p: int) -> Optional[int]:
        async with sem:
            try:
                _, w = await asyncio.wait_for(asyncio.open_connection(host, p), timeout)
                w.close()
                return p
            except Exception:
                return None

    return [p for p in await asyncio.gather(*(one(p) for p in ports)) if p]


def scan_host() -> str:
    """Where model servers are looked for: this machine, or CHITS_SCAN_HOST (in a container with ordinary port
    mapping the machine's own servers are at host.docker.internal, not at the container's localhost)."""
    return os.environ.get("CHITS_SCAN_HOST", "").strip() or "127.0.0.1"


async def scan_local(host: Optional[str] = None, ports: Optional[List[int]] = None,
                     skip: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """Find OpenAI-compatible model servers on this machine: a quick TCP sweep over the usual port ranges
    (about 2,500 ports, well under a second on localhost), then a /v1/models probe of the ports that answered."""
    host = host or scan_host()
    if ports is None and os.environ.get("CHITS_SCAN_PORTS"):
        ports = _parse_ports(os.environ["CHITS_SCAN_PORTS"])
    if ports is None:
        ports = sorted({p for a, b in SCAN_RANGES for p in range(a, b + 1)} | set(COMMON_PORTS))
    skip_set = set(skip or [])
    live = await _open_ports(host, [p for p in ports if p not in skip_set])
    results = await asyncio.gather(*(probe_endpoint(f"http://{host}:{p}/v1", timeout=3.0) for p in live))
    seen, out = set(), []
    for r in results:
        if r.get("ok") and r["base_url"] not in seen:
            seen.add(r["base_url"])
            out.append(r)
    return out
