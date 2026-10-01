"""Did the twin worlds become different civilisations? One honest comparison, with a score and post-ready text."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Optional

from ..sim.items import DESIGNS, item_name
from ..sim.world import World

TPD = 240


def _base_keys(w: World) -> Dict[str, int]:
    """Base knowledge this world found, as key -> first tick (inventions and beliefs are counted separately)."""
    out = {}
    for k, v in w.first.items():
        if not (k.startswith("recipe:") or k.startswith("design:")):
            continue
        if k.split(":", 1)[1].startswith("inv_"):
            continue
        out[k] = int(v.get("tick", 0))
    return out


def _name(w: World, key: str) -> str:
    local = w.culture_names.get(key)
    kind, k = key.split(":", 1)
    base = item_name(k, w.catalog) if kind == "recipe" else (DESIGNS[k].name if k in DESIGNS else k)
    return f'{base} ("{local}")' if local else base


def _era(w: World) -> str:
    return w.era()[1] if hasattr(w, "era") else ""


def compare(wa: World, wb: World) -> Dict[str, Any]:
    ka, kb = _base_keys(wa), _base_keys(wb)
    A, B = set(ka), set(kb)
    union, inter = A | B, A & B
    J = 1 - len(inter) / len(union) if union else 0.0
    shared = sorted(inter, key=lambda k: (min(ka[k], kb[k]), k))
    pairs = list(combinations(shared, 2))
    if len(shared) >= 2:
        disc = sum(1 for x, y in pairs if (ka[x] - ka[y]) * (kb[x] - kb[y]) < 0)
        K = disc / len(pairs)
    else:
        K = 0.0
    n_cult = len(wa.inventions) + len(wb.inventions) + len(wa.beliefs) + len(wb.beliefs)
    C = min(1.0, n_cult / 10)
    divergence = round(100 * (0.5 * J + 0.3 * K + 0.2 * C))
    race, wins = [], {wa.id: 0, wb.id: 0}
    for k in shared:
        winner = wa.id if ka[k] < kb[k] else wb.id if kb[k] < ka[k] else None
        if winner:
            wins[winner] += 1
        race.append({"key": k, "name": _name(wa, k), wa.id: ka[k] // TPD + 1, wb.id: kb[k] // TPD + 1, "winner": winner})
    day = max(wa.day, wb.day) + 1

    def world_info(w: World, keys: Dict[str, int]) -> Dict[str, Any]:
        st = w.stats()
        return {"id": w.id, "name": w.name, "label": w.label, "culture": w.culture, "day": w.day + 1,
                "population": st["population"], "generations": st["generations"], "era": _era(w),
                "discoveries": len(keys), "inventions": [i["name"] for i in w.inventions.values()],
                "beliefs": [b["name"] for b in w.beliefs.values()], "local_names": dict(w.culture_names),
                # knowledge that came by boat: what the strangers from the other island brought with them (T30)
                "contact": sorted({k for a in w.agents.values() if a.origin and a.origin != w.id for k in a.knows})}

    headline = (f"Same island, two minds: {divergence}% divergent by day {day}" if divergence
                else f"Same island, two minds: identical so far (day {day})")
    return {
        "day": day,
        "worlds": {wa.id: world_info(wa, ka), wb.id: world_info(wb, kb)},
        "shared": shared,
        "only": {wa.id: sorted(A - B, key=lambda k: (ka[k], k)), wb.id: sorted(B - A, key=lambda k: (kb[k], k))},
        "only_names": {wa.id: [_name(wa, k) for k in sorted(A - B, key=lambda k: (ka[k], k))],
                       wb.id: [_name(wb, k) for k in sorted(B - A, key=lambda k: (kb[k], k))]},
        "race": race,
        "wins": wins,
        "scores": {"knowledge": J, "order": K, "culture": C},
        "divergence": divergence,
        "headline": headline,
        "_detail": {wa.id: {"inventions": list(wa.inventions.values()), "beliefs": list(wa.beliefs.values())},
                    wb.id: {"inventions": list(wb.inventions.values()), "beliefs": list(wb.beliefs.values())}},
    }


def to_markdown(c: Dict[str, Any]) -> str:
    ids = list(c["worlds"])
    ws = c["worlds"]
    L = [f"# {c['headline']}", "", "| | " + " | ".join(ws[i]["name"] for i in ids) + " |", "|---|" + "---|" * len(ids)]
    for label, key in (("Population", "population"), ("Generations", "generations"), ("Era", "era"),
                       ("Discoveries", "discoveries")):
        L.append(f"| {label} | " + " | ".join(str(ws[i][key]) for i in ids) + " |")
    L.append("| Inventions | " + " | ".join(str(len(ws[i]["inventions"])) for i in ids) + " |")
    L.append("| Beliefs | " + " | ".join(str(len(ws[i]["beliefs"])) for i in ids) + " |")
    for i in ids:
        L += ["", f"## Only in {ws[i]['name']}", ""]
        names = c.get("only_names", {}).get(i) or c["only"][i]
        L += [f"- {n}" for n in names] or ["- (nothing yet)"]
    L += ["", "## The race", ""]
    for r in c["race"]:
        a, b = ids
        who = f"{r['winner']} first" if r["winner"] else "a tie"
        L.append(f"- {r['name']} — {ws[a]['name']} day {r[a]} · {ws[b]['name']} day {r[b]} ({who})")
    if not c["race"]:
        L.append("- (nothing found by both yet)")
    det = c.get("_detail", {})
    L += ["", "## Inventions", ""]
    for i in ids:
        inv = det.get(i, {}).get("inventions")
        if inv:
            L += [f"- {ws[i]['name']}: {x['name']} (for {x['purpose']}, by {x['by_name']})" for x in inv]
        else:
            L.append(f"- {ws[i]['name']}: " + (", ".join(ws[i]["inventions"]) or "none"))
    L += ["", "## Beliefs", ""]
    for i in ids:
        bel = det.get(i, {}).get("beliefs")
        if bel:
            L += [f'- {ws[i]["name"]}: {b["name"]} — "{b["tenet"]}" ({len(b.get("followers", []))} believe)' for b in bel]
        else:
            L.append(f"- {ws[i]['name']}: " + (", ".join(ws[i]["beliefs"]) or "none"))
    s = c["scores"]
    L += ["", f"Divergence: {c['divergence']}/100 (knowledge {s['knowledge']:.2f} · order {s['order']:.2f} · "
              f"culture {s['culture']:.2f})"]
    return "\n".join(L) + "\n"


def _standout(c: Dict[str, Any], wid: str) -> Optional[str]:
    names = c.get("only_names", {}).get(wid) or []
    if names:
        return f"only they found {names[-1]}"
    det = c.get("_detail", {}).get(wid, {})
    if det.get("inventions"):
        return f"invented the {det['inventions'][-1]['name']}"
    if c["worlds"][wid]["inventions"]:
        return f"invented the {c['worlds'][wid]['inventions'][-1]}"
    if c["worlds"][wid]["beliefs"]:
        return f"came to believe in {c['worlds'][wid]['beliefs'][-1]}"
    return None


def to_tweet(c: Dict[str, Any]) -> str:
    lines = [c["headline"]]
    for wid, w in c["worlds"].items():
        so = _standout(c, wid)
        if so:
            lines.append(f"{w['name']}: {so}")
    tail = f"Divergence {c['divergence']}/100 #LittleChits"
    text = "\n".join(lines + [tail])
    while len(text) > 280 and len(lines) > 1:
        lines[-1] = lines[-1][: max(20, len(lines[-1]) - (len(text) - 280) - 1)].rstrip() + "…"
        text = "\n".join(lines + [tail])
        if len(text) > 280:
            lines.pop()
            text = "\n".join(lines + [tail])
    return text[:280]
