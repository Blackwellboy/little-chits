"""Find the story beats in an event log. Every moment cites the events that prove it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Moment:
    kind: str
    score: int
    tick: int
    x: Optional[float]
    y: Optional[float]
    actors: List[str]
    text: str
    seqs: List[int]


CHAIN_GAP = 480


def _knowledge_name(key: str) -> str:
    return (key or "").split(":", 1)[-1].replace("_", " ")


def _moment(kind: str, score: int, evs: List[dict], actors: List[str], text: str) -> Moment:
    last = evs[-1]
    return Moment(kind, int(score), last["tick"], last.get("x"), last.get("y"), actors, text, [e["seq"] for e in evs])


def _chains(events: List[dict], names: Dict[str, str]) -> List[Moment]:
    taught = [e for e in events if e["kind"] == "learned" and (e.get("data") or {}).get("how") == "taught"]
    by_key: Dict[str, List[dict]] = {}
    for e in taught:
        by_key.setdefault(e["data"].get("knowledge", ""), []).append(e)
    out = []
    for key, evs in by_key.items():
        evs.sort(key=lambda e: e["seq"])
        # an event continues a chain if its teacher is the previous learner, soon enough
        nxt: Dict[int, dict] = {}
        has_prev = set()
        for i, e in enumerate(evs):
            for f in evs[i + 1:]:
                if f["data"].get("source") == e["actor"] and 0 <= f["tick"] - e["tick"] <= CHAIN_GAP:
                    nxt[e["seq"]] = f
                    has_prev.add(f["seq"])
                    break
        for e in evs:
            if e["seq"] in has_prev:
                continue  # only start at the head of a chain, so chains are maximal
            chain = [e]
            while chain[-1]["seq"] in nxt:
                chain.append(nxt[chain[-1]["seq"]])
            actors = [chain[0]["data"].get("source")] + [c["actor"] for c in chain]
            if len(actors) < 3:
                continue
            who = [names.get(a, a) for a in actors]
            text = f"{who[0]} taught {who[1]}" + "".join(f", who taught {w}" for w in who[2:]) + f": {_knowledge_name(key)}"
            out.append(_moment("teaching_chain", min(95, 70 + 5 * (len(actors) - 3)), chain, actors, text))
    return out


def find_moments(events: List[dict], names: Dict[str, str]) -> List[Moment]:
    events = sorted(events, key=lambda e: e["seq"])
    out: List[Moment] = []
    pioneers = set()
    for e in events:
        k, d, actor = e["kind"], e.get("data") or {}, e.get("actor")
        actors = [actor] if actor else []
        if k in ("discovery", "first"):
            out.append(_moment("first", 95 if d.get("local_name") else 90, [e], actors, e["text"]))
            if k == "discovery" and actor:
                pioneers.add(actor)
        elif k in ("contact", "war", "peace", "raid"):
            out.append(_moment(k, {"contact": 97, "war": 96, "peace": 95, "raid": 85}[k], [e], actors, e["text"]))
        elif k in ("voyage", "arrival"):
            out.append(_moment(k, 90 if k == "voyage" else 96, [e], actors, e["text"]))
        elif k in ("miracle", "revelation"):
            out.append(_moment(k, 90 if k == "miracle" else 94, [e], actors, e["text"]))
        elif k in ("militia", "theft", "fight"):
            out.append(_moment(k, {"militia": 80, "theft": 55, "fight": 60}[k], [e], actors, e["text"]))
        elif k in ("election", "elder"):
            out.append(_moment(k, 70, [e], actors, e["text"]))
        elif k == "law":
            out.append(_moment("law", 88, [e], actors, e["text"]))
        elif k == "money":
            out.append(_moment("money", 93, [e], actors, e["text"]))
        elif k == "era":
            out.append(_moment("era", 99 if d.get("era") == "Space Age" else 85, [e], actors, e["text"]))
        elif k == "launch":
            out.append(_moment("launch", 99, [e], (d.get("crew") or actors), e["text"]))
        elif k == "belief":
            out.append(_moment("belief", 90, [e], actors, e["text"]))
        elif k == "scripture":
            out.append(_moment("scripture", 88, [e], actors, e["text"]))
        elif k == "invention":
            out.append(_moment("invention", 92, [e], actors, e["text"]))
        elif k == "legacy":
            out.append(_moment("legacy", 80, [e], actors, e["text"]))
        elif k == "built" and len(d.get("builders") or []) >= 3:
            n = len(d["builders"])
            score = min(80, 55 + 5 * (n - 3)) + (15 if d.get("first") else 0)
            out.append(_moment("built_together", score, [e], list(d["builders"]), e["text"]))
        elif k == "death" and actor in pioneers:
            out.append(_moment("lost_pioneer", 85, [e], actors, e["text"]))
        elif k == "birth":
            out.append(_moment("birth", 60 if (d.get("generation") or 0) >= 2 else 40, [e], actors, e["text"]))
        elif k == "storm":
            out.append(_moment("storm", 65, [e], actors, e["text"]))
        elif k == "settlement":
            out.append(_moment("settlement", 75, [e], actors, e["text"]))
        elif k == "ambition":
            out.append(_moment("ambition", 45, [e], actors, e["text"]))
        elif k == "project_done":  # the whole village's work (sim/projects.py)
            out.append(_moment("project_done", 86, [e], list(d.get("helpers") or actors), e["text"]))
        elif k == "hint":
            out.append(_moment("hint", 70, [e], actors, e["text"]))
        elif k == "forgotten":  # the village lost something it knew (sim/lore.py)
            out.append(_moment("forgotten", 72, [e], actors, e["text"]))
    out += _chains(events, names)
    out.sort(key=lambda m: (m.score, m.tick), reverse=True)
    return out


def top_moments(events: List[dict], names: Dict[str, str], since_tick: int = 0, limit: int = 10) -> List[Moment]:
    return [m for m in find_moments(events, names) if m.tick >= since_tick][:limit]
