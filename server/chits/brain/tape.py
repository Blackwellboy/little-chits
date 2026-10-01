"""BrainTape (research plan R2, item 39): record every model request and reply, and replay a run from the recording.

A recorded reply is keyed by what was asked: the brain, the exact messages and the request settings. Replaying runs
the same code with the tape instead of the model server: if the simulation is the same, every question comes back
the same and gets the same answer, so the run reproduces exactly. If a question isn't on the tape, the replay has
diverged: that's counted (`misses`) and raised, never answered by something else.

What it tells you: rerun an old tape on new code, and any difference is the code's (physics, prompts), not the
model's randomness. Recording is for experiments and development; a live game doesn't need it.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional


class TapeMiss(RuntimeError):
    """The replay asked something the recording never did: the run has diverged."""


class RecordedFailure(RuntimeError):
    """A request that failed when it was recorded (a timeout, a server error) fails the same way on replay."""


def request_key(brain_id: str, messages: Any, max_tokens: Optional[int], temperature: Optional[float],
                extra: Optional[Dict[str, Any]], json_reply: bool) -> str:
    blob = json.dumps([brain_id, messages, max_tokens, temperature, extra or {}, bool(json_reply)], sort_keys=True,
                      ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


class BrainTape:
    def __init__(self, path, mode: str):
        if mode not in ("record", "replay"):
            raise ValueError("a tape records or replays")
        self.path = Path(path)
        self.mode = mode
        self.recorded = 0
        self.played = 0
        self.misses = 0
        self._queue: Dict[str, Deque[Dict[str, Any]]] = defaultdict(deque)
        if mode == "replay":
            for line in self.path.read_text().splitlines():
                if line.strip():
                    e = json.loads(line)
                    self._queue[e["key"]].append(e)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("")

    def record(self, key: str, brain_id: str, reply: Dict[str, Any], messages: Any = None) -> None:
        entry = {"key": key, "brain": brain_id, "n": self.recorded, "messages": messages,
                 "reply": {k: reply.get(k) for k in ("text", "latency_ms", "tokens_in", "tokens_out", "top_logprobs",
                                                     "finish_reason")}}
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self.recorded += 1

    def record_error(self, key: str, brain_id: str, error: str, messages: Any = None) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps({"key": key, "brain": brain_id, "n": self.recorded, "messages": messages,
                                "error": error}, ensure_ascii=False) + "\n")
        self.recorded += 1

    def play(self, key: str) -> Dict[str, Any]:
        q = self._queue.get(key)
        if not q:
            self.misses += 1
            self.last_miss = key
            raise TapeMiss(f"not on the tape (request {key[:12]}): the replay has diverged from the recording")
        self.played += 1
        e = q.popleft()
        if "error" in e:
            raise RecordedFailure(e["error"])
        return dict(e["reply"], queue_ms=0.0, replayed=True)

    def remaining(self) -> int:
        return sum(len(q) for q in self._queue.values())
