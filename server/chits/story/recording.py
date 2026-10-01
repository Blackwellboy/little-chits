"""The written half of an auto-recording: for each recorded day, what happened and how the chits pulled it off.

Built only from the day's events (who discovered what and how, who taught whom, what was built together, which
beliefs and leaders appeared), plus the day's chronicle page. Like the rest of story/, it only reads."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional

from ..sim.items import item_name

HOW = {
    "discovered": "by experimenting",
    "insight": "by thinking it up",
    "inspected": "by studying someone else's work",
    "observed": "by watching someone do it",
    "built": "by building one",
    "instinct": "by trial and error",
    "taught": "from a teacher",
    "read": "from a tablet",
}


def knowledge_name(key: str) -> str:
    return item_name(key.split(":", 1)[-1]) if key else "something"


def _names(ids: List[str], names: Dict[str, str], limit: int = 4) -> str:
    shown = [names.get(i, i) for i in ids[:limit]]
    more = len(ids) - len(shown)
    if more > 0:
        shown.append(f"{more} other{'s' if more > 1 else ''}")
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]


def how_they_did_it(events: List[dict], names: Dict[str, str]) -> List[str]:
    """Plain-English lines explaining the day's achievements, most important first. Each line cites the events
    it comes from as (#seq), like the chronicle."""
    evs = sorted(events, key=lambda e: e["seq"])
    lines: List[str] = []
    learned: Dict[str, List[dict]] = defaultdict(list)
    for e in evs:
        if e["kind"] == "learned" and (e.get("data") or {}).get("knowledge"):
            learned[e["data"]["knowledge"]].append(e)

    explained = set()
    for e in evs:
        d = e.get("data") or {}
        k = d.get("knowledge", "")
        if e["kind"] != "discovery" or not k:
            continue
        explained.add(k)
        who = names.get(e.get("actor", ""), "Someone")
        line = f"**{who}** worked out {knowledge_name(k)} {HOW.get(d.get('how', ''), '')}".rstrip() + f" (#{e['seq']})"
        spread = learned.get(k, [])
        if spread:
            hows = Counter(HOW.get((s.get("data") or {}).get("how", ""), "somehow") for s in spread)
            line += f", and by nightfall {len(spread)} more knew it (" + ", ".join(f"{n} {h}" for h, n in hows.most_common()) + ")"
        lines.append(line + ".")

    # knowledge that travelled today without being new: the busiest teaching routes
    routes = sorted(((k, v) for k, v in learned.items() if k not in explained), key=lambda kv: -len(kv[1]))
    for k, spread in routes[:3]:
        teachers = Counter(names.get((s.get("data") or {}).get("source", ""), "") for s in spread)
        teachers.pop("", None)
        by = f", mostly from {teachers.most_common(1)[0][0]}" if teachers else ""
        more = f"{len(spread)} more chit" + ("s" if len(spread) > 1 else "")
        lines.append(f"{knowledge_name(k).capitalize()} spread to {more}{by} (#{spread[0]['seq']}).")

    for e in evs:
        d = e.get("data") or {}
        if e["kind"] == "built" and d.get("first"):
            builders = d.get("builders") or [e.get("actor", "")]
            lines.append(f"The first {item_name(d.get('design', 'building'))} went up, built by "
                         f"{_names(builders, names)} (#{e['seq']}).")
    together = [e for e in evs if e["kind"] == "built" and (e.get("data") or {}).get("together")
                and not (e.get("data") or {}).get("first")]
    if together:
        kinds = Counter(item_name((e.get("data") or {}).get("design", "building")) for e in together)
        lines.append("Built together: " + ", ".join(f"{n} {k}{'s' if n > 1 else ''}" for k, n in kinds.most_common())
                     + f" (#{together[0]['seq']}).")

    for e in evs:
        d = e.get("data") or {}
        who = names.get(e.get("actor", ""), "Someone")
        if e["kind"] == "belief" and d.get("name"):
            lines.append(f"{who} founded a belief, *{d['name']}*: \"{d.get('tenet', '')[:140]}\" (#{e['seq']}).")
        elif e["kind"] == "invention":
            lines.append(f"{e['text']} (#{e['seq']}).")
        elif e["kind"] == "election":
            lines.append(f"{e['text']} (#{e['seq']}).")
        elif e["kind"] == "legacy":
            lines.append(f"{e['text']}: knowledge outliving its keeper (#{e['seq']}).")

    counts = Counter(e["kind"] for e in evs)
    life = [f"{counts[k]} {w if counts[k] == 1 else w + 's'}" for k, w in (("birth", "birth"), ("death", "death")) if counts[k]]
    if life:
        lines.append("Life and loss: " + ", ".join(life) + ".")
    return lines


def _strip_title(md: str) -> str:
    """A chronicle page without its title, its own sections tucked under "The day"."""
    body = md.split("\n", 1)[1] if md.startswith("# ") else md
    return "\n".join("##" + line if line.startswith("## ") else line for line in body.strip().split("\n"))


MOMENTS_HEADING = "## Moments"


def moment_line(m: dict) -> str:
    """One filmed moment as a story bullet: where and when, the event itself (cited), and the clip."""
    caption = str(m.get("caption") or m.get("text") or "").replace("[", "(").replace("]", ")")
    where = f"**{m.get('world_name') or 'World ' + str(m.get('world', '?'))}**" + (f", {m['clock']}" if m.get("clock") else "")
    cite = f" (#{m['seq']})" if m.get("seq") is not None else ""
    return f"- 🎬 {where}: {caption}{cite} · [▶ watch it live]({m.get('clip')})"


def add_moment_line(md: str, line: str) -> str:
    """Put a moment filmed after the day's page was written into that page's Moments list (made if missing)."""
    if line in md:
        return md
    lines = md.rstrip("\n").split("\n")
    if MOMENTS_HEADING in lines:
        i = lines.index(MOMENTS_HEADING) + 1
        while i < len(lines) and (not lines[i].strip() or lines[i].startswith("- ")):
            i += 1
        while i > 0 and not lines[i - 1].strip():  # after the last bullet, before the blank line
            i -= 1
        lines.insert(i, line)
    else:
        at = next((i for i, s in enumerate(lines) if s.startswith("## ")), len(lines))
        block = [MOMENTS_HEADING, "", line, ""]
        if at == len(lines):
            block = [""] + block[:-1]
        lines[at:at] = block
    return "\n".join(lines) + "\n"


def day_story(day: int, worlds: List[dict], clip: Optional[str] = None, moments: Optional[List[dict]] = None) -> str:
    """One recorded day as markdown. Each world dict has: name, label, brain, lines (how_they_did_it) and
    chronicle (that day's chronicle page, or ""). `moments` are the day's filmed moments (see moment_line)."""
    out = [f"# Day {day}", ""]
    if clip:
        out += [f"[▶ Watch day {day}]({clip})", ""]
    if moments:
        out += [MOMENTS_HEADING, ""] + [moment_line(m) for m in moments] + [""]
    for w in worlds:
        who = " · ".join(x for x in (w.get("label"), w.get("brain")) if x)
        out.append(f"## {w['name']}" + (f" ({who})" if who else ""))
        out.append("")
        out.append("### How they did it")
        out += [f"- {line}" for line in w["lines"]] or ["- A quiet day: nothing new was learned or built."]
        out.append("")
        if w.get("chronicle"):
            out.append("### The day")
            out.append(_strip_title(w["chronicle"]))
            out.append("")
    return "\n".join(out).rstrip() + "\n"
