"""The story so far: a short recap for someone who has just arrived, from the world's own record (its ages and who
reached them, its dead and the ones worth remembering, what it once knew and lost, its laws, what the island threw at
it, the rival island, and who leads now). No model is asked and nothing is invented: every line is a count or a quote."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..sim import hall as HALL
from ..sim.agent import TICKS_PER_DAY
from ..sim.items import DESIGNS
from ..sim.world import ERAS, World


def _num(n: int) -> str:
    return f"{n:,}"


def _age_days(w: World) -> Dict[str, int]:
    out = {}
    for name, key in ERAS[1:w.era()[0] + 1]:
        f = w.age_record(key)
        if f:
            out[name] = f.get("tick", 0) // TICKS_PER_DAY + 1
    return out


def lost_arts(w: World, limit: int = 4) -> List[str]:
    """Things this world once made or built that nobody alive knows how to any more."""
    base_value = w.catalog.value  # (base_value, and a content pack's items by what goes into them)

    known = {k for a in w.agents.values() for k in a.knows}
    age = {key: i for i, (_, key) in enumerate(ERAS) if key}
    out = []
    # the arts that marked an age first, the latest age first (a world that forgot iron), then the most valuable
    for key, f in sorted(w.first.items(), key=lambda kv: (-age.get(kv[0], -1), -base_value(kv[0].split(":", 1)[-1]),
                                                           kv[1].get("tick", 0))):
        if key in known or ":" not in key:
            continue
        kind, k = key.split(":", 1)
        if kind == "recipe":
            out.append(w.item_name(k))
        elif kind == "design" and k in DESIGNS:
            out.append(f"the {DESIGNS[k].name}")
    return out[:limit]


def remembered(w: World, n: int = 3) -> List[Dict[str, Any]]:
    heroes = {f.get("by") for _, key in ERAS if key and (f := w.first.get(key))}  # first makers of an age's key thing
    bios = [b for b in (HALL.biography(w, a) for a in w.dead.values()) if b]
    bios.sort(key=lambda b: (-((5 if b["id"] in heroes else 0) + 2 * len(b["inventions"]) + len(b["firsts"])
                               + len(b["deeds"]) + b["taught"] / 20 + b["renown"] / 5), b["id"]))
    return bios[:n]


def recap(w: World, counts: Optional[Dict[str, int]] = None, rival: Optional[World] = None) -> Dict[str, Any]:
    counts = counts or {}
    day = w.day + 1
    lines: List[str] = []
    from ..sim.settlements import detect

    vs = detect(w)  # (not the sim's once-a-tick cache: a request never feeds the world)
    where = (f"the village of {vs[0].name}" if len(vs) == 1 else
             f"{len(vs)} villages: " + ", ".join(v.name for v in vs[:4]) if vs else "no village yet")
    gens = max([a.generation for a in list(w.agents.values()) + list(w.dead.values())] or [0])
    lines.append(f"Day {_num(day)}. {len(w.agents)} chits live in {where}. {_num(len(w.dead))} {'has' if len(w.dead) == 1 else 'have'} died "
                 f"over {gens} generations.")
    ages = _age_days(w)
    if ages:
        lines.append("The ages so far: " + ", ".join(f"{n} (day {d})" for n, d in sorted(ages.items(), key=lambda kv: kv[1])) + ".")
    i = w.era()[0]
    if i + 1 < len(ERAS):
        kind, key = ERAS[i + 1][1].split(":", 1)
        thing = DESIGNS[key].name if kind == "design" and key in DESIGNS else w.item_name(key)
        lines.append(f"Next is the {ERAS[i + 1][0]}, when someone first makes {'a ' if kind == 'design' or ' ' in thing else ''}{thing}.")
    lost = lost_arts(w)
    if lost:
        lines.append("Once known, now forgotten: " + ", ".join(lost) + ".")
    for b in remembered(w):
        did = b["firsts"] and f"the first to {b['firsts'][0]}" or b["inventions"] and f"who invented the {b['inventions'][0]}" \
            or b["deeds"] and b["deeds"][0] or b["taught"] and f"who taught {b['taught']} chits" \
            or b["children"] and f"who had {b['children']} {'child' if b['children'] == 1 else 'children'}" \
            or f"who lived to {b['age']} days"
        if did.startswith("the first"):
            did = "who was " + did
        lines.append(f"Remembered: {b['name']}, {did}; died of {b['cause'] or 'unknown causes'} on day {b['died_day']}.")
    if counts.get("law"):
        last = w.laws[-1] if w.laws else None
        lines.append(f"{_num(counts['law'])} laws decreed" + (f"; the latest, by Chief {last['by_name']}: \u201c{last['text']}\u201d" if last else "."))
    hard = [(counts.get(k, 0), label) for k, label in (("storm", "storms"), ("drought", "droughts"), ("wolf", "wolf attacks"))]
    said = [f"{_num(n)} {label}" for n, label in hard if n]
    if said:
        lines.append("The island has thrown " + (", ".join(said[:-1]) + " and " + said[-1] if len(said) > 1 else said[0]) + " at them.")
    if rival is not None:
        ra, rd = _age_days(rival), len(rival.first)
        top = ERAS[w.era()[0]][0]
        ahead = ""
        if top in ra and top in ages and ra[top] != ages[top]:
            first = w.name if ages[top] < ra[top] else rival.name
            ahead = f" {first} reached the {top} first, by {abs(ra[top] - ages[top])} days."
        lines.append(f"Across the water, {rival.name} is in the {ERAS[rival.era()[0]][0]} with {rd} discoveries to "
                     f"{w.name}'s {len(w.first)}.{ahead}")
    lead = w.agents.get(getattr(w, "leader", "") or "")
    from ..sim.projects import of, title

    proj = of(w) or {}  # (the chief's village's project)
    if lead or proj:

        now = f"Chief {lead.name} leads" if lead else "Nobody leads"
        lines.append(f"Now: {now}" + (f", and the village is working to {title(proj)}" if proj else "") + ".")
    title_ = f"{w.name}: the story so far"
    return {"title": title_, "day": day, "lines": lines, "markdown": f"## {title_}\n\n" + "\n".join(f"- {l}" for l in lines)}
