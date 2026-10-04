"""A deterministic benchmark of the invention judge (F34): what a model might write, and what the world should say.

    python -m chits.tools.invent_bench [--json]

Instinct never invents, so an instinct A/B cannot judge the invention engine. This does: a fixed list of invention
attempts in the words a model would use (sensible ones, physically impossible ones, vague ones, and ones that name a
purpose the parts cannot serve), each with the verdict a fair judge of the physics would give. Both engines are run
over it (sim/invent.py: the composing one, and the first keyword engine behind COMPOSE = False), and the report says
how many each accepts, how many each gets right, where they differ, and what every accepted invention can do.

No world, no model and no random numbers: the same table every time.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional, Tuple

from ..sim import invent as INV

# (what the chit writes, the parts, the station it stands at, should it work, what it should be, kind of attempt)
Case = Tuple[str, Dict[str, int], Optional[str], bool, Optional[str], str]

SENSIBLE, IMPOSSIBLE, VAGUE, WRONG_PURPOSE = "sensible", "impossible", "vague", "wrong purpose"

CASES: List[Case] = [
    # ---- sensible: the parts can do it
    ("a net to catch fish", {"fiber": 2, "wood": 1}, None, True, "fishing", SENSIBLE),
    ("a pointed stick to catch fish", {"wood": 1, "sharp_stone": 1}, None, True, "fishing", SENSIBLE),
    ("a trap to catch fish", {"cord": 1, "pot": 1}, None, True, "fishing", SENSIBLE),
    ("a shoe to run fast", {"wood": 2}, None, True, "speed", SENSIBLE),
    ("a sledge to travel fast", {"wood": 2}, None, True, "speed", SENSIBLE),
    ("sandals to walk quick", {"fiber": 2, "wood": 1}, None, True, "speed", SENSIBLE),
    ("a cart to travel fast", {"wheel": 1, "wood": 1}, None, True, "speed", SENSIBLE),
    ("a knife to cut reeds", {"sharp_stone": 1, "wood": 1}, None, True, "cutting", SENSIBLE),
    ("an axe to chop trees", {"iron": 1, "wood": 1}, None, True, "cutting", SENSIBLE),
    ("a blade to cut", {"copper": 1, "wood": 1}, "workshop", True, "cutting", SENSIBLE),
    ("a hammer to break rock and dig", {"stone": 1, "wood": 1}, None, True, "digging", SENSIBLE),
    ("a pick to mine ore", {"stone": 1, "wood": 1}, None, True, "digging", SENSIBLE),
    ("a hoe to till the field", {"copper": 1, "wood": 1}, None, True, "farming", SENSIBLE),
    ("a plough to break the field", {"iron": 1, "wood": 1}, None, True, "farming", SENSIBLE),
    ("a club to fight off wolves", {"sharp_stone": 1, "wood": 1}, None, True, "defence", SENSIBLE),
    ("a sling to guard against wolves", {"stone": 1, "cord": 1}, None, True, "defence", SENSIBLE),
    ("a sack to carry berries", {"fiber": 2}, None, True, "carrying", SENSIBLE),
    ("a pack to carry more on my back", {"basket": 1, "cord": 1}, None, True, "carrying", SENSIBLE),
    ("a pack to carry food", {"basket": 1, "cord": 1}, None, True, "carrying", SENSIBLE),
    ("a barrow to haul stone", {"wheel": 1, "wood": 1}, None, True, "carrying", SENSIBLE),
    ("a cart to carry more", {"wheel": 1, "wood": 2}, None, True, "carrying", SENSIBLE),
    ("a blanket to keep warm", {"cloth": 2}, None, True, "warmth", SENSIBLE),
    ("a coat for the winter cold", {"wool": 2, "cord": 1}, None, True, "warmth", SENSIBLE),
    ("a warm cloak to wear when I farm the field", {"cloth": 2}, None, True, "warmth", SENSIBLE),
    ("a torch to light the night", {"wood": 2}, None, True, "light", SENSIBLE),
    ("a lamp to light the hut", {"charcoal": 1, "pot": 1}, None, True, "light", SENSIBLE),
    ("a lantern for the dark", {"glass": 1, "charcoal": 1}, None, True, "light", SENSIBLE),
    ("a tasty meal", {"berries": 2, "grain": 1}, None, True, "food", SENSIBLE),
    ("a stew to eat", {"fish": 1, "berries": 1}, None, True, "food", SENSIBLE),
    ("a meal cooked over the fire", {"berries": 2, "grain": 1}, "fire", True, "food", SENSIBLE),
    ("a sweet snack to carry along", {"berries": 2}, None, True, "food", SENSIBLE),
    ("a poultice to heal the sick", {"fiber": 1, "berries": 1}, None, True, "healing", SENSIBLE),
    ("a bandage for wounds", {"cloth": 1, "cord": 1}, None, True, "healing", SENSIBLE),
    ("a tonic to cure the sick", {"berries": 1, "pot": 1}, "fire", True, "healing", SENSIBLE),
    ("a drum to make music", {"stone": 1, "wood": 1}, None, True, "joy", SENSIBLE),
    ("a jewel, something pretty", {"copper": 1, "glass": 1}, None, True, "joy", SENSIBLE),
    ("a fishing net, not a weapon", {"fiber": 2, "wood": 1}, None, True, "fishing", SENSIBLE),
    # ---- physically impossible: nothing here can do that
    ("a net to catch fish", {"berries": 2}, None, False, None, IMPOSSIBLE),
    ("a cloak to keep warm", {"stone": 2}, None, False, None, IMPOSSIBLE),
    ("a knife to cut", {"sand": 1, "clay": 1}, None, False, None, IMPOSSIBLE),
    ("a wheel to travel fast", {"sand": 2}, None, False, None, IMPOSSIBLE),
    ("a torch for light", {"berries": 2}, None, False, None, IMPOSSIBLE),
    ("a lamp", {"clay": 2}, None, False, None, IMPOSSIBLE),
    ("a shield to protect me", {"grain": 1, "stone": 1}, None, False, None, IMPOSSIBLE),
    # ---- a purpose these parts cannot serve (they could make something else)
    ("an axe to chop wood", {"berries": 1, "grain": 1}, None, False, None, WRONG_PURPOSE),
    ("a blanket to keep warm", {"berries": 1, "wood": 1}, None, False, None, WRONG_PURPOSE),
    ("something to heat the hut", {"wood": 1, "stone": 1}, None, False, None, WRONG_PURPOSE),
    ("a bag to carry things", {"fiber": 1, "stone": 1}, None, False, None, WRONG_PURPOSE),
    ("food for winter", {"wood": 1, "berries": 1}, None, False, None, WRONG_PURPOSE),
    ("a remedy to cure the sick", {"fish": 1, "wood": 1}, None, False, None, WRONG_PURPOSE),
    ("a knife to cut", {"copper": 1, "wood": 1}, None, False, None, WRONG_PURPOSE),  # (unworked copper: no edge)
    # ---- vague: nobody could say what it is for
    ("fly to the moon", {"wood": 2}, None, False, None, VAGUE),
    ("something useful", {"stone": 1, "wood": 1}, None, False, None, VAGUE),
    ("a thing", {"fiber": 2}, None, False, None, VAGUE),
    ("to make life better", {"stone": 1, "wood": 1}, None, False, None, VAGUE),
    ("a drum", {"wood": 1}, None, False, None, VAGUE),  # (one piece is not an invention)
    ("a raft", {"wood": 5}, None, False, None, VAGUE),
]


def _run(compose: bool) -> List[Dict[str, Any]]:
    was = INV.COMPOSE
    INV.COMPOSE = compose
    try:
        out = []
        for text, bag, station, want_ok, want_pid, kind in CASES:
            v = INV.verdict(bag, text, None, (station,) if station else ())
            right = v["ok"] == want_ok and (not want_ok or v["purpose"] == want_pid)
            out.append({"text": text, "bag": bag, "station": station, "kind": kind, "want_ok": want_ok, "want": want_pid,
                        "ok": v["ok"], "purpose": v["purpose"], "effect": v["effect"], "rule": v["rule"],
                        "feedback": v["feedback"], "right": right})
        return out
    finally:
        INV.COMPOSE = was


def bench() -> Dict[str, Any]:
    """Both engines over CASES: {"cases", "old", "new"} where each engine has its rows, how many it accepted and how
    many verdicts were right, by kind of attempt."""
    res: Dict[str, Any] = {"cases": len(CASES)}
    for name, compose in (("old", False), ("new", True)):
        rows = _run(compose)
        kinds: Dict[str, List[int]] = {}
        for r in rows:
            k = kinds.setdefault(r["kind"], [0, 0])
            k[0] += r["right"]
            k[1] += 1
        res[name] = {"rows": rows, "accepted": sum(r["ok"] for r in rows), "right": sum(r["right"] for r in rows),
                     "by_kind": {k: {"right": v[0], "of": v[1]} for k, v in kinds.items()}}
    return res


def _bag(bag: Dict[str, int]) -> str:
    return " + ".join(f"{n} {k}" if n > 1 else k for k, n in sorted(bag.items()))


def report(res: Dict[str, Any]) -> str:
    L = [f"Invention benchmark: {res['cases']} attempts", ""]
    L.append("| engine | accepted | right verdicts | " + " | ".join(res["new"]["by_kind"]) + " |")
    L.append("|---|---|---|" + "---|" * len(res["new"]["by_kind"]))
    for name, label in (("old", "keywords (first engine)"), ("new", "composition")):
        e = res[name]
        L.append(f"| {label} | {e['accepted']} | {e['right']}/{res['cases']} | "
                 + " | ".join(f"{v['right']}/{v['of']}" for v in e["by_kind"].values()) + " |")
    L += ["", "Where the engines differ, or one is wrong:", ""]
    L.append("| attempt | parts | should | keywords | composition |")
    L.append("|---|---|---|---|---|")
    for o, n in zip(res["old"]["rows"], res["new"]["rows"]):
        if o["right"] and n["right"] and o["ok"] == n["ok"]:
            continue
        say = lambda r: (f"{r['purpose']}" if r["ok"] else f"refused ({r['purpose'] or 'not understood'})") + ("" if r["right"] else " WRONG")
        at = f" at a {o['station']}" if o["station"] else ""
        L.append(f"| {o['text']} | {_bag(o['bag'])}{at} | {o['want'] if o['want_ok'] else 'refuse'} | {say(o)} | {say(n)} |")
    L += ["", "What each invention the composing engine accepts can do:", ""]
    L.append("| attempt | parts | it is | it does |")
    L.append("|---|---|---|---|")
    for n in res["new"]["rows"]:
        if n["ok"]:
            at = f" at a {n['station']}" if n["station"] else ""
            L.append(f"| {n['text']} | {_bag(n['bag'])}{at} | {INV.RULE[n['rule']].what} | {'; '.join(INV.effect_words(n['effect']))} |")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print the full result as JSON instead of the report")
    args = ap.parse_args(argv)
    res = bench()
    print(json.dumps(res, indent=1, sort_keys=True) if args.json else report(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
