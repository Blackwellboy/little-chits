"""Daily chronicle pages, built only from what happened. A model may tell the day vividly, but a validator
throws out anything the facts don't support: unknown names, invented numbers, and made-up heroics."""

from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .moments import find_moments

_CITE = re.compile(r"\(#(\d+)\)")
_WORD = re.compile(r"[A-Za-z]+")

# word families a narration may not use unless the facts back them up (see T12 "truth layer")
CAUSATION = ("because", "so that", "which led", "caused", "saved", "thanks to")
EMOTION = ("courageous", "courageously", "brave", "bravely", "frightened", "afraid", "angry", "loved", "desperate",
           "desperately", "determined")
LEADERSHIP = ("led", "rallied", "chief", "leader", "commanded")
SUPERLATIVE = ("first", "best", "greatest", "only")

COUNT_WORDS = {"discovery": ("discovery", "discoveries"), "built": ("building finished", "buildings finished"),
               "birth": ("birth", "births"), "death": ("death", "deaths"), "learned": ("lesson passed on", "lessons passed on")}


def daily_facts(world: dict, day: int, events: List[dict], stats: Optional[dict], names: Dict[str, str]) -> dict:
    evs = sorted((e for e in events if e["tick"] // 240 + 1 == day), key=lambda e: e["seq"])
    counts: Dict[str, int] = {}
    for e in evs:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    actors = sorted({names.get(e["actor"], e["actor"]) for e in evs if e.get("actor")})
    moments = [asdict(m) for m in find_moments(evs, names)[:6]]
    return {
        "world": world.get("id"), "world_name": world.get("name", world.get("id")), "brain": world.get("brain", ""),
        "day": day, "counts": counts, "stats": stats or {}, "agents": actors,
        "events": [{"seq": e["seq"], "kind": e["kind"], "text": e["text"]} for e in evs if e.get("importance", 0) >= 2][:40],
        "moments": moments,
    }


def render_markdown(facts: dict) -> str:
    c = facts["counts"]
    bits = []
    for kind, (one, many) in COUNT_WORDS.items():
        n = c.get(kind, 0)
        if n:
            bits.append(f"{n} {one if n == 1 else many}")
    lines = [f"# {facts['world_name']} — Day {facts['day']}", ""]
    if facts.get("brain"):
        lines += [f"*Minds: {facts['brain']}*", ""]
    lines += [" · ".join(bits) if bits else "A quiet day.", "", "## Highlights", ""]
    if facts["moments"]:
        for m in facts["moments"]:
            lines.append(f"- {m['text']} " + " ".join(f"(#{s})" for s in m["seqs"][:3]))
    elif facts["events"]:
        for e in facts["events"][:12]:
            lines.append(f"- {e['text']} (#{e['seq']})")
    else:
        lines.append("- Nothing of note.")
    st = facts.get("stats") or {}
    lines += ["", "## Numbers", "",
              f"- Population: {st.get('population', '?')}",
              f"- Discoveries: {st.get('discoveries', '?')}",
              f"- Structures: {st.get('structures', '?')}"]
    return "\n".join(lines) + "\n"


def _has_phrase(text: str, phrase: str) -> Optional[str]:
    m = re.search(r"\b" + re.escape(phrase) + r"\b", text, re.I)
    return m.group(0) if m else None


def validate_narration(text: str, facts: dict, known_names: Set[str]) -> List[str]:
    problems: List[str] = []
    cited = [int(x) for x in _CITE.findall(text)]
    ok_seqs = {e["seq"] for e in facts.get("events", [])}
    for m in facts.get("moments", []):
        ok_seqs |= set(m.get("seqs", []))
    if not cited:
        problems.append("no citation: cite events like (#123)")
    for c in cited:
        if c not in ok_seqs:
            problems.append(f"cites (#{c}), which isn't one of today's events")
    words = set(_WORD.findall(text))
    present = set(facts.get("agents", []))
    for n in sorted(known_names):
        if n in words and n not in present:
            problems.append(f"{n} wasn't part of today's events")
    body = _CITE.sub(" ", text)
    allowed = {str(facts.get("day", ""))}
    for v in list(facts.get("counts", {}).values()) + list((facts.get("stats") or {}).values()):
        if isinstance(v, (int, float)):
            allowed.add(str(int(v)))
    blob = " ".join(e["text"] for e in facts.get("events", [])) + " " + " ".join(m.get("text", "") for m in facts.get("moments", []))
    allowed |= set(re.findall(r"\d+", blob))
    for num in re.findall(r"\d+", body):
        if num not in allowed:
            problems.append(f"the number {num} isn't in the facts")
    kinds = {e.get("kind") for e in facts.get("events", [])} | {m.get("kind") for m in facts.get("moments", [])}
    for p in CAUSATION:
        w = _has_phrase(body, p)
        if w:
            problems.append(f'unsupported causation: "{w}"')
    if "speech" not in kinds:
        for p in EMOTION:
            w = _has_phrase(body, p)
            if w:
                problems.append(f'unsupported emotion: "{w}"')
    if not kinds & {"election", "elder", "law"}:
        for p in LEADERSHIP:
            w = _has_phrase(body, p)
            if w:
                problems.append(f'unsupported leadership: "{w}"')
    for p in SUPERLATIVE:
        w = _has_phrase(body, p)
        if w and not (p == "first" and kinds & {"first", "discovery"}):
            problems.append(f'unsupported superlative: "{w}"')
    return problems


HISTORIAN = ("You are the historian of a small island of creatures called chits. Write 100-200 words telling this "
             "day vividly but strictly factually. Use only the facts given: only the names listed, only numbers "
             "that appear, no motives, emotions or causes that aren't stated, and cite every event you mention "
             "as (#seq). Reply with the text only.")


async def narrate(brain, facts: dict, known_names: Set[str]) -> Optional[str]:
    import json

    body = json.dumps({k: facts[k] for k in ("world_name", "day", "counts", "agents", "events", "moments")}, default=str)
    msgs = [{"role": "system", "content": HISTORIAN}, {"role": "user", "content": body}]
    try:
        for attempt in range(2):
            res = await brain.chat(msgs, max_tokens=400, temperature=0.7)
            text = _clean(res["text"])
            probs = validate_narration(text, facts, known_names)
            if not probs:
                return text
            msgs = msgs + [{"role": "assistant", "content": text},
                           {"role": "user", "content": "Fix these problems and reply with the corrected text only: " + "; ".join(probs[:8])}]
    except Exception:
        return None
    return None


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    if text.startswith("{"):
        try:
            import json

            obj = json.loads(text)
            text = str(obj.get("text") or obj.get("story") or obj.get("narration") or "")
        except ValueError:
            pass
    return text.strip()


def write_day(data_dir: Path, facts: dict, narration: Optional[str] = None) -> Path:
    p = Path(data_dir) / "stories" / str(facts["world"]) / f"day-{facts['day']:03d}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    md = render_markdown(facts)
    if narration:
        md += f"\n## The day, told\n\n{narration}\n"
    p.write_text(md)
    return p
