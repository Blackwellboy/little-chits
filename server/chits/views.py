"""Serialisers for the observer. Presentation only; they never mutate the world."""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from .sim.actions import describe_step
from .sim.agent import TICKS_PER_DAY, Agent
from .sim.items import DESIGNS, ITEMS, RECIPES, STORES, all_knowledge_keys, item_name
from .sim.world import Structure, World


def knowledge_name(k: str, w: Optional[World] = None) -> str:
    kind, key = k.split(":", 1)
    return item_name(key, w.catalog if w else None) if kind == "recipe" else DESIGNS[key].name


def agent_brief(w: World, a: Agent) -> Dict[str, Any]:
    carry = None
    best = 0
    for k, n in a.inventory.items():
        it = w.item(k)
        if it and not it.tool and not it.carry_bonus and n > best:
            carry, best = k, n
    tool = None
    for cls in ("axe", "pick", "spear", "light"):
        tool = tool or a.best_tool(cls)
    return {
        "id": a.id, "name": a.name, "x": a.x, "y": a.y, "hue": a.hue, "act": a.activity, "emote": a.emote,
        "say": a.say, "think": a.thinking, "carry": carry, "tool": tool, "child": a.is_child(w.tick),
        "basket": a.has("basket"), "hp": round(a.health), "hunger": round(a.hunger), "brain": a.brain,
        "src": "model" if a.plan_source.startswith("model") else "instinct",
    }


def structure_view(s: Structure, w: World) -> Dict[str, Any]:
    d = DESIGNS[s.design]
    founder = w.agents.get(s.founder) or w.dead.get(s.founder)
    return {
        "id": s.id, "design": s.design, "name": d.name, "x": s.x, "y": s.y, "w": s.w, "h": s.h,
        "complete": s.complete, "progress": round(min(1.0, s.work_done / max(1.0, s.work_total)), 3),
        "needs": s.needs, "durability": round(s.durability, 1), "lit": s.lit, "fuel": round(s.fuel),
        "planted": s.planted, "growth": round(s.growth, 2), "stored": sum(s.storage.values()),
        "storage": s.storage if s.design in STORES or s.design == "mine" else None, "tablets": len(s.shelf),
        "founder": founder.name if founder else None, "builders": len(s.builders), "ruined": s.ruined,
        "worked_until": s.worked_until, "produced": s.produced or None,
        "upgrade": _upgrade_view(s),
    }


def _upgrade_view(s: Structure) -> Optional[Dict[str, Any]]:
    """A home being rebuilt bigger: into what, what it still needs, and how far the work is."""
    up = s.upgrade
    if not up:
        return None
    return {"to": up["to"], "name": DESIGNS[up["to"]].name, "needs": dict(up.get("needs") or {}),
            "progress": round(min(1.0, up.get("work", 0.0) / max(1.0, up.get("total", 1.0))), 3)}


def belief_list(w: World) -> List[Dict[str, Any]]:
    out = []
    for b in w.beliefs.values():
        out.append({**b, "day": b["tick"] // 240 + 1, "count": len(b["followers"]),
                    "tablets": sum(1 for t in w.tablets.values() if t.knowledge == f"belief:{b['id']}"),
                    "shrines": sum(1 for s in w.structures.values() if s.design == "shrine" and s.belief == b["id"] and s.functional)})
    return out


def animals_compact(w: World) -> List[list]:
    return [[a["id"], a["kind"], a["x"], a["y"], 1 if a["tame"] else 0] for a in w.animals.values()]


def ground_view(w: World) -> List[Dict[str, Any]]:
    out = []
    for tile, pile in w.ground.items():
        items = {k: n for k, n in pile.items() if k != "_t" and n > 0}
        if not items:
            continue
        x, y = tile.split(",")
        top = max(items, key=lambda k: (ITEMS[k].weight if k in ITEMS else 1, items[k]))
        out.append({"x": int(x), "y": int(y), "items": items, "icon": (w.item(top).icon if w.item(top) else "") or "📦",
                    "name": w.item_name(top)})
    return out


def b64(data) -> str:
    return base64.b64encode(bytes(data)).decode()


def world_meta(w: World) -> Dict[str, Any]:
    return {"id": w.id, "name": w.name, "label": w.label, "culture": w.culture, "flags": w.flags, "size": w.w,
            "seed": w.seed, "uuid": w.uuid, "epoch": w.epoch, "leader": w.leader, "laws": w.laws}


def snapshot(w: World, events_limit: int = 80) -> Dict[str, Any]:
    trails = [i for i, v in enumerate(w.traffic) if v > 30]
    try:
        amt = bytes(w.res_amt)  # ~1 ms; the clamping generator below took ~100 ms on a 512 island
    except (TypeError, ValueError):
        amt = bytes(min(255, max(0, int(v))) for v in w.res_amt)
    return {
        "world": world_meta(w),
        "signs": list(w.signs.values()),
        "inventions": list(w.inventions.values()),
        "beliefs": belief_list(w),
        "ground": ground_view(w),
        "animals": animals_compact(w),
        "tiles": b64(w.tiles), "res_kind": b64(w.res_kind), "res_amt": b64(amt),
        "roads": sorted(w.roads), "trails": trails,
        "structures": [structure_view(s, w) for s in w.structures.values()],
        "agents": [agent_brief(w, a) for a in w.agents.values()],
        "tablets": [{"id": t.id, "x": t.x, "y": t.y} for t in w.tablets.values() if not t.in_structure],
        "events": [e.to_dict() for e in list(w.events)[-events_limit:]],
        "clock": w.clock(), "stats": w.stats(), "history": w.history[-200:],
    }


def agent_detail(w: World, a: Agent, brain_label: str = "") -> Dict[str, Any]:
    t = w.tick
    everyone = {**w.dead, **w.agents}

    def nm(aid: Optional[str]) -> Optional[str]:
        o = everyone.get(aid or "")
        return o.name if o else None

    knows = []
    for k, v in sorted(a.knows.items(), key=lambda kv: kv[1]["tick"]):
        kind, key = k.split(":", 1)
        knows.append({
            "key": k, "kind": kind, "name": knowledge_name(k, w), "how": v["how"], "from": nm(v.get("from")),
            "day": v["tick"] // 240 + 1,
            "detail": w.catalog.describe(w.recipe(key)) if kind == "recipe" else
            ", ".join(f"{n} {item_name(m)}" for m, n in DESIGNS[key].materials),
            "icon": w.item(key).icon if kind == "recipe" else "",
        })
    rels = sorted(((v, k) for k, v in a.affinity.items() if abs(v) >= 3), reverse=True)[:10]
    home = w.structures.get(a.home or "")
    return {
        **agent_brief(w, a),
        "alive": a.alive, "age": round(a.age(t if a.alive else a.died), 1), "generation": a.generation,
        "parents": [nm(p) for p in a.parents], "died": a.died, "cause": a.cause_of_death,
        "needs": {"hunger": round(a.hunger), "energy": round(a.energy), "warmth": round(a.warmth),
                  "health": round(a.health), "mood": round(a.mood)},
        "traits": a.traits, "personality": a.personality(),
        "inventory": [{"key": k, "name": w.item_name(k), "n": n, "icon": w.item(k).icon, "tool": bool(w.item(k).tool)}
                      for k, n in sorted(a.inventory.items())],
        "load": a.load(), "capacity": a.capacity(),
        "knows": knows, "lessons": a.lessons,
        "lesson_sources": {l: a.lesson_sources.get(l, []) for l in a.lessons}, "failed": a.failed_experiments[-8:],
        "memories": [m.to_dict() for m in a.memories[-30:]][::-1],
        "relations": [{"id": k, "name": nm(k), "affinity": round(v)} for v, k in rels if nm(k)],
        "skills": {k: round(v, 1) for k, v in sorted(a.skills.items(), key=lambda kv: -kv[1])},
        "goal": a.goal, "thought": a.thought, "plan": [describe_step(s) for s in a.plan],
        "last_choice": a.last_choice if a.last_choice and t - a.last_choice.get("tick", -10 ** 9) < 480 else None,
        "plan_state": [{"desc": describe_step(s), "reflex": bool(s.get("_reflex")), "filler": bool(s.get("_filler"))} for s in a.plan],
        "plan_source": a.plan_source, "plan_id": a.plan_id, "objective": a.objective, "objective_since": a.objective_since, "ambition": a.ambition, "last_result": a.last_result, "brain_label": brain_label or a.brain,
        "home": {"id": home.id, "name": DESIGNS[home.design].name, "x": home.x, "y": home.y} if home else None,
        "stats": a.stats, "decisions": a.decisions, "job": a.job, "job_source": a.job_source,
        "leader": a.id == w.leader, "origin": a.origin, "leader_title": ("chief" if w.flags.get("say") else "elder") if a.id == w.leader else "",
        "belief": ({"id": a.belief, "name": w.beliefs[a.belief]["name"], "tenet": w.beliefs[a.belief]["tenet"]}
                   if a.belief in w.beliefs else None),
        "want": (a.want or {}).get("text", ""), "renown": round(a.renown, 1), "famous": _famous_id(w) == a.id,
    }


def _at_risk(w: World) -> List[Dict[str, Any]]:
    """What only one living chit knows how to make: the village's knowledge at risk (sim/lore.py)."""
    from .sim import lore

    return [{"what": w.item_name(k.split(":", 1)[1]), "keeper": a.name, "keeper_id": a.id, "old": lore.old(w, a),
             "age": round(a.age(w.tick)), "lifespan": round(a.lifespan / TICKS_PER_DAY)}
            for k, a in lore.at_risk(w)[:8]]


def _food_days(w: World) -> float:
    from .sim.food import food_days

    return food_days(w)


def _famous_id(w: World) -> str:
    from .sim.wants import famous

    star = famous(w)
    return star.id if star else ""


def knowledge_table(worlds: List[World]) -> List[Dict[str, Any]]:
    rows = []
    # a content pack's recipes are knowledge like any other (every world of a match has the same pack)
    packed = next((w for w in worlds if w.catalog.pack_recipes), None)
    extra = [f"recipe:{k}" for k in packed.catalog.pack_recipes if k not in ITEMS] if packed else []
    for k in all_knowledge_keys() + extra:
        kind, key = k.split(":", 1)
        it = (ITEMS.get(key) or (packed.item(key) if packed else None)) if kind == "recipe" else None
        row = {"key": k, "kind": kind, "name": knowledge_name(k, packed if k in extra else None),
               "icon": it.icon if it else "", "worlds": {}}
        any_ = False
        for w in worlds:
            f = w.first.get(k)
            knowers = sum(1 for a in w.agents.values() if k in a.knows)
            worked = sum(1 for a in w.agents.values() if a.knows.get(k, {}).get("status") == "worked")
            if f or knowers:
                any_ = True
            row["worlds"][w.id] = {"first_by": f["name"] if f else None, "first_day": f["tick"] // 240 + 1 if f else None,
                                   "knowers": knowers, "worked": worked, "population": len(w.agents),
                                   "local_name": w.culture_names.get(k)}
        row["discovered"] = any_
        if kind == "design" and key in ("campfire", "hut"):
            row["starting"] = True
        rows.append(row)
    return rows


def discovered(w: World, k: str) -> bool:
    """Has this world found a thing? The knowledge table's own test: someone found it first, or someone alive knows
    it (the two designs every chit starts with have no first finder)."""
    return k in w.first or any(k in a.knows for a in w.agents.values())


def _effects(w: World, key: str) -> List[str]:
    """What an item does by itself, each line from one field of its entry in the item table."""
    from .sim.items import ACTION_USES, GATHER_RULES

    it = w.item(key)
    out = []
    if it.food:
        out.append(f"Food: eating one restores {it.food:g} hunger.")
    if it.tool:
        out.append(f"Tool: works as {'an' if it.tool[0] in 'aeiou' else 'a'} {it.tool} with power {it.tool_power:g}.")
        for raw, rule in GATHER_RULES.items():
            if rule["tool"] == it.tool:
                out.append(f"{'Needed to gather' if rule['requires'] else 'Helps to gather'} {item_name(raw)}.")
    if it.carry_bonus:
        out.append(f"Carrying: its holder can carry {it.carry_bonus} more.")
    if "wearable" in it.props:
        out.append("Wearable: a chit can wear it.")
    if key in ACTION_USES:
        out.append(f"Use: {ACTION_USES[key]}.")
    return out


def encyclopedia(w: World, k: str) -> Optional[Dict[str, Any]]:
    """What a thing this world has discovered is for. An item: its properties, what it is made from, what it does
    by itself and what it goes into. A building: what it does, what it takes and how big it is. None for what the world
    hasn't found, and the lists of uses name only recipes and buildings it has found (the rest is a bare count): the
    observer is told nothing the world doesn't know, and nothing here is read by a chit or a brain."""
    kind, _, key = k.partition(":")
    if kind not in ("recipe", "design") or not discovered(w, k):
        return None
    first = w.first.get(k)
    out: Dict[str, Any] = {"key": k, "kind": kind, "name": knowledge_name(k, w), "world": w.id,
                           "local_name": w.culture_names.get(k),
                           "first_by": first["name"] if first else None,
                           "first_day": first["tick"] // TICKS_PER_DAY + 1 if first else None}
    recipes = {**RECIPES, **w.catalog.recipes}

    def named(key: str, n: Optional[int] = None) -> Dict[str, Any]:
        it = w.item(key)
        d = {"key": key, "name": w.item_name(key), "icon": it.icon if it else ""}
        return d if n is None else {**d, "n": n}

    if kind == "recipe":
        it, r = w.item(key), w.recipe(key)
        if it is None or r is None:
            return None
        inv = w.inventions.get(key)
        in_recipes = [rk for rk, rr in recipes.items() if any(i == key for i, _ in rr.inputs)]
        in_designs = [dk for dk, d in DESIGNS.items() if key in d.material_map]
        known_r = [rk for rk in in_recipes if discovered(w, f"recipe:{rk}")]
        known_d = [dk for dk in in_designs if discovered(w, f"design:{dk}")]
        out.update(icon=it.icon, props=list(it.props), weight=it.weight,
                   made_from={"inputs": [named(i, n) for i, n in r.inputs], "station": r.station, "makes": r.qty},
                   effects=_effects(w, key),
                   used_in_recipes=[named(rk) for rk in known_r],
                   used_in_buildings=[{"key": dk, "name": DESIGNS[dk].name, "n": DESIGNS[dk].material_map[key]}
                                      for dk in known_d],
                   undiscovered_uses=len(in_recipes) - len(known_r) + len(in_designs) - len(known_d),
                   invention={"purpose": inv["purpose"], "purpose_text": inv.get("purpose_text", ""),
                              "by": inv.get("by_name", ""), "day": inv["tick"] // TICKS_PER_DAY + 1} if inv else None)
        return out
    d = DESIGNS[key]
    made_here = [rk for rk, rr in recipes.items() if d.station and rr.station == d.station]
    known_here = [rk for rk in made_here if discovered(w, f"recipe:{rk}")]
    out.update(icon="", blurb=d.blurb, materials=[named(m, n) for m, n in d.materials], size=list(d.size),
               work=d.work, station=d.station, min_pop=d.min_pop,
               made_here=[named(rk) for rk in known_here], undiscovered_uses=len(made_here) - len(known_here))
    return out


def day_chronicle(w: World, events: List[Dict[str, Any]], day: int) -> Dict[str, Any]:
    """A grounded daily digest: only events that happened, ranked by importance."""
    evs = [e for e in events if e["tick"] // 240 + 1 == day]
    hi = sorted([e for e in evs if e["importance"] >= 2], key=lambda e: (-e["importance"], e["seq"]))[:14]
    hi.sort(key=lambda e: e["seq"])
    counts: Dict[str, int] = {}
    for e in evs:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    hist = next((h for h in w.history if h.get("day") == day + 1), None) or next((h for h in w.history if h.get("day") == day), None)
    bits = []
    if counts.get("discovery"):
        bits.append(f"{counts['discovery']} discover{'y' if counts['discovery'] == 1 else 'ies'}")
    if counts.get("built"):
        bits.append(f"{counts['built']} structure{'s' if counts['built'] > 1 else ''} finished")
    if counts.get("learned"):
        bits.append(f"{counts['learned']} lessons passed on")
    if counts.get("birth"):
        bits.append(f"{counts['birth']} birth{'s' if counts['birth'] > 1 else ''}")
    if counts.get("death"):
        bits.append(f"{counts['death']} death{'s' if counts['death'] > 1 else ''}")
    if counts.get("speech"):
        bits.append(f"{counts['speech']} things said")
    return {"day": day, "summary": (", ".join(bits) or "a quiet day").capitalize() + ".", "highlights": hi,
            "counts": counts, "stats": hist}


def milestones(w: World, road: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The road to the next age (projects.road) as a checklist for the observer: each step says what to do (discover
    a recipe, make enough of a known material, build a building) and whether it is done. A "make" step is a made
    material the village knows but has too little of for a building on the road, counted the way the road counts it."""
    if not road:
        return None
    from .sim import projects

    _, recipes = projects._known(w)
    steps: List[Dict[str, Any]] = []
    for s in road["steps"]:
        if s["kind"] == "recipe":
            steps.append({"action": "discover", "key": f"recipe:{s['key']}", "name": s["name"], "done": s["done"],
                          "detail": ""})
            continue
        if not s["done"]:
            for m, n in DESIGNS[s["key"]].materials:
                have = projects.stock(w, m, s["key"]) if m in RECIPES and m in recipes else n
                if have < n:
                    steps.append({"action": "make", "key": f"recipe:{m}", "name": item_name(m), "done": False,
                                  "detail": f"{have} of {n} for the {s['name']}"})
        idea = s["needs"].split("; ")[0] if s["needs"].startswith("nobody") else ""
        steps.append({"action": "build", "key": f"design:{s['key']}", "name": s["name"], "done": s["done"], "detail": idea})
    return {"age": road["age"], "steps": steps, "done": sum(1 for s in steps if s["done"]), "total": len(steps)}


def progress(w: World, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """🧭 Is this world getting anywhere? Its place on the road to space, what everyone is busy with right now,
    what they are working towards, and how the last two days' achievements came about."""
    from .sim.world import ERAS
    from .story.recording import how_they_did_it

    now, _ = w.era()
    ladder = []
    for name, key in ERAS:
        first = w.first.get(key) if key else None
        ladder.append({"name": name, "needs": item_name(key.split(":", 1)[1]) if key else "",
                       # an age counts once its key thing exists, even if an earlier one was skipped
                       "reached": key is None or first is not None, "by": (first or {}).get("name", ""),
                       "day": first["tick"] // 240 + 1 if first else None})
    doing: Dict[str, int] = {}
    aims: Dict[str, int] = {}
    for a in w.agents.values():
        act = (a.activity or "idle").split(" ")[0].strip(".,") or "idle"
        doing[act] = doing.get(act, 0) + 1
        if a.objective:
            aim = a.objective.strip()[:90]
            aims[aim] = aims.get(aim, 0) + 1
    names = {a.id: a.name for a in list(w.agents.values()) + list(w.dead.values())}
    day = w.tick // 240 + 1
    recent = []
    for d in (day, day - 1):
        lines = how_they_did_it([e for e in events if e["tick"] // 240 + 1 == d], names) if d >= 1 else []
        if lines:
            recent.append({"day": d, "lines": lines})
    st = w.stats()
    from .sim import projects, research
    from .sim.wants import famous

    star = famous(w)
    civ = getattr(w, "civic", None) or {}
    road = projects.road(w)
    return {
        "project": projects.view(w), "road": road, "milestones": milestones(w, road),
        "food_days": _food_days(w), "at_risk": _at_risk(w),
        "research": {"insight": round(civ.get("insight", 0.0), 1), "next_idea": research.threshold(w) if civ else 0,
                     "hints": [{"text": h["text"], "day": h["tick"] // 240 + 1, "by": h.get("by_name", ""),
                                "found": bool(h.get("found"))} for h in reversed(civ.get("hints", [])[-4:])]},
        "famous": {"name": star.name, "renown": round(star.renown, 1)} if star else None,
        "day": day, "era": {"index": now, "name": ERAS[now][0], "of": len(ERAS) - 1},
        "next": ladder[now + 1] if now + 1 < len(ladder) else None, "ladder": ladder,
        "doing": sorted(doing.items(), key=lambda kv: -kv[1]),
        "aims": sorted(aims.items(), key=lambda kv: -kv[1])[:6],
        "recent": recent,
        "counts": {"population": len(w.agents), "discoveries": st.get("discoveries", 0),
                   "structures": st.get("structures", 0), "beliefs": len(w.beliefs), "known": st.get("knowledge", 0)},
    }


# ---------------------------------------------------------------------------------------------- family and spread
def _who(w: World, a: Agent) -> Dict[str, Any]:
    return {"id": a.id, "name": a.name, "alive": a.alive, "born_day": max(0, a.born) // TICKS_PER_DAY + 1,
            "died_day": a.died // TICKS_PER_DAY + 1 if a.died >= 0 else None,
            "cause": a.cause_of_death or None, "generation": a.generation}


def family(w: World, aid: str) -> Optional[Dict[str, Any]]:
    """A chit's family, living and dead: grandparents, parents, siblings, children and grandchildren."""
    everyone = {**w.dead, **w.agents}
    a = everyone.get(aid)
    if a is None:
        return None
    kids = lambda ids: sorted((o for o in everyone.values() if set(o.parents) & set(ids)), key=lambda o: (o.born, o.id))
    parents = [everyone[p] for p in a.parents if p in everyone]
    grand = [everyone[g] for p in parents for g in p.parents if g in everyone]
    children = kids([a.id])
    siblings = [o for o in kids(a.parents) if o.id != a.id] if a.parents else []
    return {"self": _who(w, a), "grandparents": [_who(w, x) for x in grand], "parents": [_who(w, x) for x in parents],
            "siblings": [_who(w, x) for x in siblings], "children": [_who(w, x) for x in children],
            "grandchildren": [_who(w, x) for x in kids([c.id for c in children])]}


def spread(w: World, key: str, depth: int = 6) -> Dict[str, Any]:
    """How the village came to know a thing: who found it, and from each knower, whom it passed to and how (taught,
    watched, read, raised...). Built from each chit's own record of where it learned it, living or dead."""
    everyone = {**w.dead, **w.agents}
    knowers = {a.id: a for a in everyone.values() if key in a.knows}
    parent: Dict[str, Optional[str]] = {}
    for a in knowers.values():
        src = None if a.origin else a.knows[key].get("from")  # over the sea, "from" is an id in its homeland
        parent[a.id] = src if src in knowers and src != a.id else None
    for aid in sorted(parent, key=lambda i: (knowers[i].knows[key].get("tick", 0), i)):
        seen, x = set(), aid
        while parent.get(x) is not None and x not in seen:
            seen.add(x)
            x = parent[x]
        if x in seen:  # it came back round: a loop with no finder; it starts here instead
            parent[x] = None
    kids: Dict[Optional[str], List[Agent]] = {}
    for aid, src in parent.items():
        kids.setdefault(src, []).append(knowers[aid])

    def node(a: Agent, d: int) -> Dict[str, Any]:
        k = a.knows[key]
        below = sorted(kids.get(a.id, []), key=lambda o: (o.knows[key].get("tick", 0), o.id))
        return {**_who(w, a), "how": k.get("how"), "day": (k.get("tick") or 0) // TICKS_PER_DAY + 1,
                "worked": k.get("status") == "worked",
                "passed_to": [node(o, d + 1) for o in below] if d < depth else [], "more": len(below) if d >= depth else 0}

    roots = sorted(kids.get(None, []), key=lambda o: (o.knows[key].get("tick", 0), o.id))
    hows: Dict[str, int] = {}
    for a in knowers.values():
        hows[a.knows[key].get("how") or "?"] = hows.get(a.knows[key].get("how") or "?", 0) + 1
    return {"key": key, "name": w.item_name(key.split(":", 1)[1]) if key.startswith("recipe:") else key.split(":", 1)[-1],
            "knowers": len(knowers), "alive": sum(1 for a in knowers.values() if a.alive), "by_how": hows,
            "roots": [node(a, 0) for a in roots]}


def hall(w: World, limit: int = 60) -> List[Dict[str, Any]]:
    """The hall of ancestors: a biography for each chit that mattered, the most recently departed first."""
    from .sim import hall as HALL

    out = []
    for a in sorted(w.dead.values(), key=lambda a: (-(a.died or 0), a.id)):
        b = HALL.biography(w, a)
        if b is not None:
            b.pop("_by", None)
            out.append(b)
            if len(out) >= limit:
                break
    return out


def eras(w: World) -> Dict[str, Any]:
    """The world's age and, for each age it has reached, who first made its key thing: the renderer's statues."""
    from .sim.world import ERAS

    i, name = w.era()
    heroes = []
    for era, key in ERAS[1:i + 1]:
        f = w.first.get(key or "")
        if f:
            heroes.append({"era": era, "who": f.get("name") or "someone", "day": f.get("tick", 0) // TICKS_PER_DAY + 1})
    return {"index": i, "name": name, "heroes": heroes}

