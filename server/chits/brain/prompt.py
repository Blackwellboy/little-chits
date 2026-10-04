"""Build the prompt a model sees: a short, vivid, *local* description of the scene.

This is deliberately written like a scene in a story rather than a JSON dump of
server fields. It only contains what this chit could plausibly know: what's in
sight, what it carries, what it has learned, remembers and has heard.
"""

from __future__ import annotations

import random
import zlib
from typing import Any, Dict, List, Tuple

from ..sim import buildings as BLD
from ..sim import terrain as T
from ..sim.actions import FOODS as _FOODS, STATION_REACH
from ..sim.agent import Agent
from ..sim.items import DESIGNS, ITEMS, LIBRARIES, RECIPES, STATIONS, STORES, item_name

SIGHT = 10
# Bump whenever the prompt text changes, so run manifests and decision records say which prompt a model saw.
PROMPT_VERSION = "2026-10-04.7"


def _dir(dx: int, dy: int) -> str:
    if dx == 0 and dy == 0:
        return "here"
    ns = "N" if dy < 0 else ("S" if dy > 0 else "")
    ew = "W" if dx < 0 else ("E" if dx > 0 else "")
    if abs(dx) > 2 * abs(dy):
        ns = ""
    if abs(dy) > 2 * abs(dx):
        ew = ""
    return ns + ew


def _where(a: Agent, x: float, y: float) -> str:
    dx, dy = int(round(x - a.x)), int(round(y - a.y))
    d = max(abs(dx), abs(dy))
    if d == 0:
        return "right here"
    return f"{d} tiles {_dir(dx, dy)} at ({int(round(x))},{int(round(y))})"


def _level(v: float, words: Tuple[str, str, str, str], cuts: Tuple[int, int, int] = (15, 35, 70)) -> str:
    if v < cuts[0]:
        return words[0]
    if v < cuts[1]:
        return words[1]
    if v < cuts[2]:
        return words[2]
    return words[3]


def verb_guide(world) -> str:
    lines = [
        '{"do":"gather","what":"wood|stone|fiber|berries|clay|sand|ore|iron ore|fish|seeds","qty":5}  (copper ore and iron ore need a pick, fish needs a spear)',
        '{"do":"eat"} or {"do":"eat","what":"berries"}',
        '{"do":"sleep"}  (best at home at night)',
        '{"do":"craft","what":"<item you know how to make>","qty":1}',
        '{"do":"work","at":"kiln"}  (work a shift at a kiln, furnace, workshop, forge, factory, mill, loom or fire: it turns stored materials into goods; add "what" to choose which)',
        '{"do":"experiment","with":["item","item"],"at":"fire|kiln|furnace|workshop|forge|factory|mill|loom","name":"<what you would call it>"}  (try combining 1-5 carried items, one on its own only at a station; the same item twice counts, and amounts matter; "at" and "name" optional; this is how new things are discovered, and the first to discover something names it)',
        '{"do":"invent","with":["item","item"],"name":"<your name for it>","purpose":"<what it is for>","at":"fire|workshop"}  (imagine something new from 2-4 carried items of up to 3 kinds. What the parts can do decides what it can be, each part doing one job: an edge or a hard head on something long is a tool, things that bind make a net, a sack or a wrap, something that burns in or on a holder is a light, edible parts are a dish, something that rolls under a frame carries or speeds. Better material makes it stronger. "at" is optional: at a workshop metal can be worked into a head, over a fire a dish or a remedy is cooked, and a thing made that way needs that station to be made again. Your purpose chooses among what the parts allow; if they cannot do it, nothing is used up and you are told what they could make. It understands purposes like catching fish, cutting, digging, carrying, keeping warm, light, food, defence against wolves, farming, healing, speed, or joy)',
        '{"do":"build","what":"<structure you know>"}  (starts a site or joins one nearby; delivers your materials and works on it)',
        '{"do":"help","site":"<site id>"}  (bring materials / labour to someone\'s construction)',
        '{"do":"upgrade","to":"longhouse|brick house|two-storey house"}  (rebuild your own home bigger where it stands: a hut becomes a longhouse or brick house, either of those a two-storey house; everyone living there stays, and a crowded home has fewer children)',
        '{"do":"build","what":"outpost","near":"x,y"}  (a camp beside far ore, sand or clay: gather there and store it in the camp, sleep there on long trips, carry it home later)',
        '{"do":"build","what":"bridge","near":"x,y"}  (planks over the nearest 1-3 tiles of water: the far bank, and the sand, clay or ore on it, come within walking reach)',
        '{"do":"store","what":"all|<item>"}  {"do":"take","what":"<item>","qty":3}  (at a stockpile)',
        '{"do":"give","to":"<name>","what":"<item>","qty":1}',
        '{"do":"trade","to":"<name>","give":{"<item>":3},"get":{"<item>":1}}  (barter: they accept if the deal is worth it to them)',
        '{"do":"steal","target":"<stockpile id>","what":"<item>","qty":3}  (take from someone else\'s stockpile; guards may catch you and others will remember)',
        '{"do":"guard","target":"<structure id>"}  (keep watch over it for a while)  {"do":"fight","to":"<name>"}  (a scuffle: it hurts and leaves grudges, nobody dies)',
    ]
    if world.flags.get("say"):
        lines.append('{"do":"say","to":"<name>|all","text":"..."}  (nearby chits hear and remember it)')
    if world.flags.get("teach"):
        lines.append('{"do":"teach","to":"<name>","what":"<item or structure you know>"}')
    if world.flags.get("write"):
        lines.append('{"do":"write","what":"<item or structure you know> | belief"}  (needs a clay tablet; best at a library; "belief" writes down your belief\'s teachings)')
    lines.append('{"do":"mark","what":"food|wood|stone|clay|ore|fish|danger|home|build|meet"}  (put up a sign here for others; costs 1 wood)')
    lines.append('{"do":"shelter"}  (get indoors or by a fire in bad weather)')
    lines.append('{"do":"prospect","what":"ore|sand|clay","dir":"N|NE|E|SE|S|SW|W|NW"}  (a long trip out to find what is '
                 'scarce near home; you look about widely, remember what you find and come back'
                 + (', and tell those at home' if world.flags.get("say") else '') + ')')
    if getattr(world, "contact", False):
        lines.append('{"do":"sail","intent":"explore|trade|raid|settle"}  (take a boat across the sea to the other island; strangers there sail home the same way)')
        lines.append('{"do":"trade","at":"stores"}  (a trader from over the sea: swap the goods you carried over at the stores here '
                     'for goods of the same worth, then {"do":"sail"} home in your boat)')
    lines.append('{"do":"hunt","what":"deer|wolf"}  (needs a spear; deer give meat)  {"do":"tame"}  (lure a wild sheep into a pen with grain or berries; tame sheep give wool)')
    lines.append('{"do":"pray"} or {"do":"pray","target":"<shrine id>"}  (spend quiet time at a shrine)')
    if world.flags.get("say"):
        lines.append('{"do":"preach"}  (speak your belief to the chits around you; some may come to share it)')
    lines += [
        '{"do":"read"}  (learn from tablets at a library)',
        '{"do":"study"}  (research at a library that holds tablets; enough study gives the village\'s scholars an idea for something new to make)',
        '{"do":"inspect","target":"<structure id | chit name | carried item>"}  (study it to try to learn how it was made)',
        '{"do":"explore","dir":"N|S|E|W|NE|NW|SE|SW"}  {"do":"go","to":"x,y | name | id"}',
        '{"do":"refuel","target":"<campfire id>"}  (feed wood to a fire)  {"do":"plant"}  {"do":"harvest"}  (farms)',
        '{"do":"repair","target":"<id>"}  {"do":"drop","what":"<item>","qty":1}  {"do":"pickup","what":"<item>"}  {"do":"rest"}',
        '{"do":"repair","what":"<worn metal tool>"}  (re-haft it at a workshop with one wood: as good as new)  '
        '{"do":"smelt","what":"<metal tool>"}  (melt it back into its metal at a furnace)',
    ]
    from ..sim.agent import JOBS

    lines.append(f'Your reply may also include "job":"<one of {", ".join(JOBS)}>" to take up (or change) a trade.')
    return "\n".join("- " + l for l in lines)


def system_prompt(world, a: Agent) -> str:
    culture = (
        "In this world chits can talk, teach each other and write on tablets."
        if world.flags.get("say") else
        "In this world chits CANNOT talk, teach or write to each other. You can only learn from what you see: "
        "watching others work, studying the things and buildings they leave behind."
    )
    # Everything up to "Steps:" is the same for every chit in a world, and the chit's own lines come last, so
    # model servers can reuse the shared start of the prompt (prefix caching) instead of re-reading it each time.
    return f"""You are the mind of a small creature called a chit, living with other chits in a wild world.
Nobody tells you what to become — you decide.
The world follows real, consistent rules of nature. Only what nature allows succeeds; you'll be told what happened.
There is no recipe book. New items are discovered by EXPERIMENTING (combining carried items, sometimes at a fire,
kiln, furnace or workshop), by watching others, and by studying things they made. Item properties are real clues.
Tools change what you can do (an axe cuts more wood, a pick is needed for ore). Seasons turn; winter is cold and
nothing grows, so food must be stored and shelters and fires matter. {culture}

Reply with ONE JSON object and nothing else:
{{"thought":"one short sentence in your own voice","objective":"what you are working towards (keep it until done)","goal":"a few words","plan":[step, step, ...]}}
"objective" is lasting (e.g. "somewhere warm before winter"): repeat it or leave it out while it still holds; change it
only when you've achieved or abandoned it. "goal" is just this plan.
The plan has 2-6 steps carried out in order, covering the next few hours of your life. Think ahead:
gather what a step needs before the step that needs it. Steps:
{verb_guide(world)}

You are {a.name}. Your nature: {a.personality()}."""


def item_use(it) -> str:
    """What a tool or carried thing does for its holder, in a few words (the models were never told)."""
    return {
        "axe": f"x{it.tool_power:g} wood per swing",
        "pick": f"needed for copper ore, x{it.tool_power:g} stone",
        "spear": "catch fish, hunt deer",
        "light": "light and warmth at night",
        "weapon": "hunt and defend",
    }.get(it.tool or "", f"+{it.carry_bonus} carrying" if it.carry_bonus else "a tool")


def food_around(world, a: Agent, radius: int = 30) -> str:
    """The village's food at a glance. Chits saw farms one by one and never the whole: World A kept 241 seeds in
    its stockpiles and no food, with 27 empty farms and 4 ripe ones nobody harvested, and its people went hungry."""
    stored = seeds = 0
    ripe = growing = empty = 0
    for s in world.structures_near(a.x, a.y, radius):
        if s.design in STORES and s.functional:
            stored += sum(n for k, n in s.storage.items() if k in _FOODS)
            seeds += s.storage.get("seeds", 0)
        elif s.design == "farm" and s.functional:
            if s.planted and s.growth >= 1:
                ripe += 1
            elif s.planted:
                growing += 1
            else:
                empty += 1
    if not (stored or seeds or ripe or growing or empty):
        return ""
    parts = [f"{stored} food stored" if stored else "no food stored"]
    if seeds:
        parts.append(f"{seeds} seeds stored")
    farms = [f"{n} {w}" for n, w in ((ripe, "ripe (harvest them)"), (growing, "growing"), (empty, "empty (plant 2 seeds in each)")) if n]
    if farms:
        parts.append("farms: " + ", ".join(farms))
    return "; ".join(parts) + "."


def store_line(world, a: Agent) -> str:
    from ..sim import food

    return food.scene_line(world, a) or ""


def village_lines(world, a: Agent) -> List[str]:
    """The village's project and its scholars' hints (sim/projects.py, sim/research.py), one line each."""
    from ..sim import projects, research

    if not hasattr(world, "civic"):
        return []
    from ..sim import pioneers

    trek = pioneers.scene_line(world, a)
    line = projects.scene_line(world, a)
    return ([trek] if trek else []) + ([line] if line else []) + research.scene_lines(world, a)


CHIEF_SYSTEM = ("You are the chief of a small village of creatures. Choose the one thing the whole village works "
                "on next. Answer with the letter of your choice only.")


def chief_project_messages(world, a: Agent, options: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """The village's next project, put to its chief as a one-letter choice."""
    from ..sim import projects

    rows = [f"{LETTERS[i]}) {projects.option_words(o)} ({o['why']})" for i, o in enumerate(options)]
    body = (f"You are {a.name}, chief of {world.name}. Your nature: {a.personality()}.\n"
            + (f"Your ambition: {a.ambition}\n" if getattr(a, "ambition", "") else "")
            + (f"{store_line(world, a)}\n" if store_line(world, a) else "")
            + "What should the village work on together next?\n" + "\n".join(rows) + "\nAnswer with one letter.")
    return [{"role": "system", "content": CHIEF_SYSTEM}, {"role": "user", "content": body}]


VOTE_SYSTEM = ("You are a creature in a small village choosing its chief. Back the one you want to lead. Answer with "
               "the letter of your choice only.")
TRADE_SYSTEM = ("You are a creature in a small village. Someone offers you a trade: take it or turn it down. Answer "
                "with the letter of your choice only.")


def _feeling(a: Agent, o: Agent) -> str:
    rel = a.affinity.get(o.id, 0.0)
    if o.id in a.parents or a.id in o.parents:
        return "family"
    return ("a close friend" if rel > 30 else "a friend" if rel >= 10 else "you dislike them" if rel < -10
            else "you hardly know them")


def vote_messages(world, a: Agent, cands: List[Agent]) -> List[Dict[str, str]]:
    """An election, put to a voter as a one-letter choice (sim/ballots.py)."""
    rows = []
    for i, o in enumerate(cands):
        bits = [f"age {o.age(world.tick):.0f}"]
        if getattr(o, "job", ""):
            bits.append(o.job)
        bits.append(_feeling(a, o))
        if o.id == getattr(world, "leader", ""):
            bits.append("chief now")
        if o.deeds:
            bits.append(o.deeds[-1])
        rows.append(f"{LETTERS[i]}) {o.name} ({'; '.join(bits)})")
    body = (f"You are {a.name}. Your nature: {a.personality()}.\n"
            + (f"{store_line(world, a)}\n" if store_line(world, a) else "")
            + f"{world.name} is choosing its chief. Who do you back?\n" + "\n".join(rows) + "\nAnswer with one letter.")
    return [{"role": "system", "content": VOTE_SYSTEM}, {"role": "user", "content": body}]


def trade_messages(world, a: Agent, trader: Agent, give: Dict[str, int], get: Dict[str, int]) -> List[Dict[str, str]]:
    """A trade offered to `a`, put to it as accept (A) or refuse (B)."""
    def words(bag):
        return ", ".join(f"{n} {world.item_name(k)}" for k, n in bag.items())

    have = "; ".join(f"you have {a.inventory.get(k, 0)} {world.item_name(k)}" for k in list(get) + list(give))
    hunger = _level(a.hunger, ("starving", "hungry", "fed", "full"), (15, 45, 75))
    body = (f"You are {a.name}. Your nature: {a.personality()}. You are {hunger}.\n"
            f"{trader.name} ({_feeling(a, trader)}) offers you {words(give)} for your {words(get)}. ({have}.)"
            + (" You're at the market." if world.near_market(a.x, a.y) else "")
            + "\nA) accept the trade\nB) refuse it\nAnswer with one letter.")
    return [{"role": "system", "content": TRADE_SYSTEM}, {"role": "user", "content": body}]


def lore_line(world, a: Agent) -> str:
    from ..sim import lore

    return lore.scene_line(world, a) or ""


def want_line(a: Agent) -> str:
    from ..sim.wants import scene_line

    return scene_line(a)



def loop_line(world, a: Agent) -> str:
    """The same step has failed for the same reason again and again: say so (play only; an experiment's model gets
    the world as it is, and the loop is only recorded, see diag.step_failed)."""
    from .. import diag

    loop = a.__dict__.get("_loop")
    if not loop or loop[2] < diag.LOOP_N or world.__dict__.get("_mind_strict"):
        return ""
    return (f"NOTE: '{loop[0]}' has now failed {loop[2]} times in a row for the same reason. Doing it again won't "
            f"work: do something different first.")

def scene(world, a: Agent) -> str:
    t = world.tick
    c = world.clock()
    hh = int(c["hour"])
    mm = int((c["hour"] - hh) * 60)
    temp = world.temperature()
    feel = "freezing" if temp < 0.15 else "cold" if temp < 0.42 else "mild" if temp < 0.75 else "warm"
    lines: List[str] = []
    wx = getattr(world, "weather", "clear")
    wline = ""
    if wx != "clear":
        wline = " " + world.WEATHER_TEXT.get(wx, "") + (" You are under cover." if world.sheltered(a) else " You are out in it.")
    lines.append(f"Day {c['day']}, {c['season']} (day {c['day_of_season']} of 3), {hh:02d}:{mm:02d}{' — night' if c['night'] else ''}. It is {feel}.{wline}")
    if c["season"] == "autumn":
        lines.append("Winter is coming soon: nothing will grow and nights will be bitter.")
    if hasattr(world, "era"):
        lines.append(f"- Your people live in the {world.era()[1]}.")
    strangers = [o for o in world.agents_near(a.x, a.y, SIGHT, exclude=a.id) if getattr(o, "origin", "") and o.origin != world.id][:3]
    for o in strangers:
        why = f" They came to {o.voyage_intent}." if getattr(o, "voyage_intent", "") else ""
        lines.append(f"- A stranger is among you: {o.name}, from across the sea (from World {o.origin}).{why}")
    for oid, rel in sorted(getattr(world, "relations", {}).items()):
        if rel.get("met"):
            lines.append(f"- The people of World {oid}: {rel['state']}")
    lead = world.agents.get(getattr(world, "leader", "") or "")
    if lead:
        if world.flags.get("say"):
            lines.append("- You are the chief." if lead is a else f"- Your chief is {lead.name}.")
        else:
            lines.append(f"- {lead.name} is the elder everyone looks to." if lead is not a else "- You are the elder everyone looks to.")
    laws = list(reversed(laws_in_force(world)))[:3]
    for law in laws:
        lines.append(f"- LAW (by {law['by_name']}): {law['text']}")
    if laws:  # a chief's decree is a custom; chits read it as a law of nature and let it run their lives
        lines.append("  (Laws are customs your chief decreed, not laws of nature: weigh them against your own needs and plans.)")
    lines += [f"- {x}" for x in village_lines(world, a)]
    if getattr(world, "currency", ""):
        lines.append(f"- Money here: {world.item_name(world.currency)} (most trades go through it)")
    food = food_around(world, a)
    if food:
        lines.append(f"- Food around here: {food}")
    stores = store_line(world, a)
    if stores:
        lines.append(f"- {stores}")
    news = getattr(world, "challenge", None) or {}
    if news.get("text"):
        lines.append(f"- NEWS: {news['text']}")
    if getattr(world, "fair_days", 0):
        lines.append(f"- TRADE FAIR: for {world.fair_days} more day{'s' if world.fair_days != 1 else ''} boats can cross to the other island")
    age = a.age(t)
    lines.append("")
    vil = world.settlement_of(a) if hasattr(world, "settlement_of") else None
    rank = getattr(vil, "rank", "village")
    where = f" in the {rank if rank in ('town', 'city') else 'village'} of {vil.name}" if vil else ""
    job = f" You work as a {a.job}." if getattr(a, "job", "") else ""
    lines.append(f"YOU: {a.name}, {age:.0f} days old{' (a child)' if a.is_child(t) else ''}, at ({a.x},{a.y}){where} on {T.TILE_NAMES[world.tile(a.x, a.y)]}.{job}")
    if a.objective:
        since = max(1, a.objective_since // 240 + 1) if a.objective_since >= 0 else c["day"]
        lines.append(f"YOUR OBJECTIVE (since day {since}): {a.objective}")
    if a.ambition:
        lines.append(f"YOUR AMBITION: {a.ambition}")
    if want_line(a):
        lines.append(want_line(a))
    if lore_line(world, a):
        lines.append(lore_line(world, a))
    bel = getattr(world, "beliefs", {}).get(a.belief)
    if bel:
        lines.append(f'YOUR BELIEF: {bel["name"]} — "{bel["tenet"]}"')
    lines.append(
        # "hungry" up to 45: chits only have children when fed above 45, and at 36 the word "fine" meant model-
        # driven chits never ate until starving (World B died out of old age with no births)
        f"Hunger {a.hunger:.0f}/100 ({_level(a.hunger, ('starving!', 'hungry', 'fine', 'full'), (15, 45, 75))}), "
        f"energy {a.energy:.0f} ({_level(a.energy, ('exhausted!', 'tired', 'ok', 'rested'))}), "
        f"warmth {a.warmth:.0f} ({_level(a.warmth, ('freezing!', 'cold', 'ok', 'warm'))}), health {a.health:.0f}."
    )
    inv = ", ".join(f"{n} {world.item_name(k)}{_worn(a, k, world)}" for k, n in sorted(a.inventory.items())) or "nothing"
    full = " — your hands are FULL: store or drop something before gathering more" if a.free_space() <= 0 else ""
    lines.append(f"Carrying ({a.load()}/{a.capacity()}): {inv}.{full}")
    tools = [f"{world.item_name(k)} ({item_use(world.item(k))})" for k in a.inventory
             if world.item(k).tool or world.item(k).carry_bonus]
    if tools:
        lines.append(f"Tools in hand: {', '.join(tools)}.")
    home = world.structures.get(a.home or "")
    if home:
        lines.append(f"Home: {DESIGNS[home.design].name} {home.id}, {_where(a, *home.center())}.")
    else:
        lines.append("You have no home yet.")
    # knowledge
    def _untried(k: str) -> str:
        st = a.knows[k].get("status")
        return f" ({st}, untried)" if st in ("told", "seen") else ""

    def _local(k: str) -> str:
        n = getattr(world, "culture_names", {}).get(k)
        return f' (called "{n}" here)' if n else ""

    recipes = [world.catalog.describe(world.recipe(k.split(':', 1)[1])) + _local(k) + _untried(k) for k in a.knows if k.startswith("recipe:")]
    # what each building is for: models only saw materials, and never learned a brick house is warmer or a road faster
    designs = [
        f"{DESIGNS[d].name} ({', '.join(f'{n} {world.item_name(m)}' for m, n in DESIGNS[d].materials)}"
        + (f": {DESIGNS[d].blurb}" if DESIGNS[d].blurb else "") + ")"
        for d in (k.split(':', 1)[1] for k in a.knows if k.startswith("design:"))
        if d != "boat" or getattr(world, "contact", False)  # a boat goes nowhere while the islands can't meet
    ]
    lines.append("")
    lines.append("YOU KNOW HOW TO MAKE: " + ("; ".join(recipes) if recipes else "nothing yet — experiment!"))
    lines.append("YOU KNOW HOW TO BUILD: " + "; ".join(designs))
    mine = [inv for known in (getattr(world, "inventions", {}), getattr(world, "foreign", {}))  # (its own world's, and
            for k, inv in known.items() if f"recipe:{k}" in a.knows][:6]  # what it brought over the sea)
    if mine:
        lines.append("- Inventions you know: " + "; ".join(
            f"{inv['name']} ({' + '.join(f'{n} {world.item_name(m)}' if n > 1 else world.item_name(m) for m, n in sorted(inv['inputs'].items()))}{' at a ' + inv['station'] if inv.get('station') else ''}, for {inv['purpose']}{_does(inv)})"
            for inv in mine))
    fam = sorted(a.familiar)[:16]
    if fam:
        lines.append("Things you've handled and their properties: " + "; ".join(f"{world.item_name(k)} ({', '.join(world.item(k).props)})" for k in fam if world.item(k)))
    sk = sorted(((v, k) for k, v in a.skills.items() if v >= 5), reverse=True)[:4]
    if sk:
        lines.append("Your skills: " + ", ".join(f"{k} {v:.0f}" for v, k in sk))
    if a.lessons:
        lines.append("")
        lines.append("LESSONS YOU'VE LEARNED:")
        lines += [f"- {l}" for l in a.lessons[-6:]]
    if a.failed_experiments:
        lines.append("Experiments that did nothing: " + "; ".join(a.failed_experiments[-10:]) + ".")
    others = [k for k, _ in world.village_failed(a).most_common(12) if k not in a.failed_experiments][:6]
    if others:
        lines.append("Others around here already tried these, with no luck: " + "; ".join(others) + ".")
    stale = stale_days(world)
    if a.failed_experiments or stale >= 2:
        fresh = untried_pairs(world, a)
        if fresh:
            lines.append("Combinations of things you've handled that you have never tried: " + "; ".join(fresh) + ".")
    if stale >= STALE_DAYS and a.home and a.hunger > 30 and not world.is_night:
        # a settled world can spend every plan on upkeep and never try anything new (World A: 21 days, 0 crafts)
        lines.append(f"Nothing new has been made or discovered around here for {stale} days. You have a roof and "
                     "food: this is a good time to experiment with what you carry, or to invent something.")
    mems = a.recall(8, keywords=[a.goal] if a.goal else None, now=t)
    if mems:
        lines.append("")
        lines.append("MEMORIES (oldest first):")
        for m in mems:
            ago = (t - m.tick) / 10.0
            lines.append(f"- {m.text} ({'just now' if ago < 1 else f'{ago:.0f}h ago'})")
    # surroundings
    lines.append("")
    lines.append(f"AROUND YOU (within {SIGHT} tiles):")
    res_lines = []
    for kind in ("berries", "wood", "stone", "fiber", "clay", "sand", "ore", "iron_ore", "fish"):
        p = world.nearest_resource(a.x, a.y, kind, SIGHT)
        if p:
            res_lines.append(f"{world.item_name(kind)} {_where(a, *p)}")
    lines.append("- Resources: " + ("; ".join(res_lines) if res_lines else "none in sight"))
    others = world.agents_near(a.x, a.y, SIGHT, exclude=a.id)[:7]
    if others:
        bits = []
        for o in others:
            rel = a.affinity.get(o.id, 0)
            relw = " (friend)" if rel > 30 else (" (family)" if o.id in a.parents or a.id in o.parents else "")
            # what they visibly carry: things they made, and any food or big stack (so a barter can be offered;
            # showing only made things left trade at 3 in 169 world-days)
            made = [world.item_name(k) for k, n in o.inventory.items() if n > 0 and world.recipe(k)][:2]
            stock = [f"{n} {world.item_name(k)}" for k, n in sorted(o.inventory.items(), key=lambda kv: -kv[1])
                     if not world.recipe(k) and (n >= 5 or (n >= 2 and k in _FOODS))][:2]
            carry = made + stock
            extra = f", holding {', '.join(carry)}" if carry else ""
            bits.append(f"{o.name}{relw} {_where(a, o.x, o.y)}, {o.activity}{extra}")
        lines.append("- Chits: " + "; ".join(bits))
    near = world.structures_near(a.x, a.y, SIGHT + 4)
    # at most two campfires (lit ones first): with 200 old fires around, the ten nearest things were all burned-out
    # campfires and the chit never saw the kiln or stockpile a little further off
    fires = sorted((s for s in near if s.design == "campfire"), key=lambda s: not s.lit)[:2]
    sts = [s for s in near if s.design != "campfire" or s in fires][:10]
    for s in sts:
        d = DESIGNS[s.design]
        who = world.agents.get(s.founder) or world.dead.get(s.founder)
        by = f" by {who.name}" if who else ""
        if not s.complete:
            need = ", ".join(f"{n} {world.item_name(k)}" for k, n in s.needs.items())
            prog = int(100 * s.work_done / max(1, s.work_total))
            lines.append(f"- CONSTRUCTION SITE {s.id}: {d.name}{by}, {_where(a, *s.center())}; " + (f"still needs {need}" if need else f"all materials in, {prog}% built"))
            continue
        state = []
        if s.ruined:
            state.append("in ruins")
        elif s.durability < 50:
            state.append("needs repair")
        if s.design == "campfire":
            state.append(f"lit, fuel {s.fuel:.0f}" if s.lit else "burned out")
        if s.design == "farm":
            state.append("ripe!" if s.planted and s.growth >= 1 else (f"growing {int(s.growth * 100)}%" if s.planted else "empty, needs seeds"))
        if s.design in STORES:
            inv = ", ".join(f"{n} {world.item_name(k)}" for k, n in sorted(s.storage.items(), key=lambda kv: -kv[1])[:8])
            state.append(f"holds {inv}" if inv else "empty")
        if s.design in LIBRARIES:
            state.append(f"{len(s.shelf)} tablets")
        if s.design == "shrine" and s.name:
            state.append(s.name + (" (your belief)" if s.belief and s.belief == a.belief else ""))
        if s.id == a.home:
            state.append("your home")
        state += BLD.state_words(world, s, a)
        known = "" if a.knows_design(s.design) else " (you don't know how to build this)"
        lines.append(f"- {d.name.capitalize()} {s.id}{by}, {_where(a, *s.center())}{': ' + ', '.join(state) if state else ''}{known}")
    signs = sorted((g for g in getattr(world, "signs", {}).values() if max(abs(g["x"] - a.x), abs(g["y"] - a.y)) <= SIGHT),
                   key=lambda g: max(abs(g["x"] - a.x), abs(g["y"] - a.y)))[:5]
    if signs:
        lines.append("- Signs: " + "; ".join(f'"{g["symbol"]}" {_where(a, g["x"], g["y"])} by {g["author_name"]}' for g in signs))
    beasts = sorted((x for x in getattr(world, "animals", {}).values() if max(abs(x["x"] - a.x), abs(x["y"] - a.y)) <= SIGHT),
                    key=lambda x: max(abs(x["x"] - a.x), abs(x["y"] - a.y)))[:6]
    if beasts:
        def _beast(x) -> str:
            d = max(abs(x["x"] - a.x), abs(x["y"] - a.y))
            where = _dir(x["x"] - a.x, x["y"] - a.y)
            if x["kind"] == "wolf":
                return f"a WOLF {d} tiles {where}!"
            return f"a {'tame ' if x['tame'] else ''}{x['kind']} {where}"
        lines.append("- Animals: " + ", ".join(_beast(x) for x in beasts))
    piles = world.piles_near(a.x, a.y, SIGHT)[:4] if hasattr(world, "piles_near") else []
    if piles:
        lines.append("- On the ground: " + "; ".join(
            ", ".join(f"{n} {world.item_name(k)}" for k, n in p.items() if k != "_t" and n > 0) + f" at ({x},{y})"
            for x, y, p in piles))
    tabs = [tb for tb in world.tablets.values() if tb.in_structure is None and max(abs(tb.x - a.x), abs(tb.y - a.y)) <= SIGHT]
    if tabs:
        lines.append(f"- {len(tabs)} inscribed tablet(s) lying on the ground nearby")
    here = world.stations_at(a.x, a.y)
    if here:
        lines.append(f"- You are standing at a: {', '.join(sorted(here))}")
    lines.append("")
    if a.plan:
        from ..sim.actions import describe_step
        lines.append("You are currently finishing: " + describe_step(a.plan[0]) + ". Your next plan starts after that.")
    heard = a.spoken_to
    if heard and t - heard.get("tick", 0) < 240 and heard.get("id") in world.agents:
        ago = (t - heard["tick"]) / 10.0
        lines.append(f'{heard["name"]} spoke to you {"just now" if ago < 1 else f"{ago:.0f}h ago"}: "{heard["text"]}". '
                     f'Answer them with {{"do":"say","to":"{heard["name"]}","text":"..."}} if you have something to say.')
    if a.last_result:
        lines.append("LAST RESULT: " + a.last_result)
        loop = loop_line(world, a)
        if loop:
            lines.append(loop)
    lines.append("What do you do next? Reply with the JSON object only.")
    return "\n".join(lines)


LETTERS = "ABCDEFGHI"


def choice_scene(world, a: Agent) -> str:
    """What a chit needs in order to choose (about a third of the full scene): the compact scene plus the weather,
    its objective, who spoke to it, the village's food, the chief's law and what it has never tried."""
    base = compact_scene(world, a).rsplit("\nReply with the JSON plan.", 1)[0]
    extra: List[str] = []
    wx = getattr(world, "weather", "clear")
    if wx != "clear":
        extra.append(world.WEATHER_TEXT.get(wx, "") + (" You are under cover." if world.sheltered(a) else " You are out in it."))
    if a.objective:
        extra.append(f"Your objective: {a.objective}")
    if getattr(a, "ambition", ""):
        extra.append(f"Your ambition: {a.ambition}")
    if want_line(a):
        extra.append(want_line(a))
    if lore_line(world, a):
        extra.append(lore_line(world, a))
    extra += village_lines(world, a)[:2]
    heard = a.spoken_to
    if heard and world.tick - heard.get("tick", 0) < 240 and heard.get("id") in world.agents:
        extra.append(f'{heard["name"]} said to you: "{heard["text"]}"')
    food = food_around(world, a)
    if food:
        extra.append(f"Food around here: {food}")
    stores = store_line(world, a)
    if stores:
        extra.append(stores)
    news = getattr(world, "challenge", None) or {}
    if news.get("text"):
        extra.append(f"NEWS: {news['text']}")
    for law in list(reversed(laws_in_force(world)))[:1]:
        extra.append(f"Chief's law (a custom, not nature): {law['text']}")
    fresh = untried_pairs(world, a)
    if fresh:
        extra.append("Never tried: " + "; ".join(fresh))
    return base + ("\n" + "\n".join(x[:240] for x in extra) if extra else "")


OWN_IDEA = "something else: my own idea"
CHOICE_SYSTEM = ("You are the mind of a small creature called a chit, in a wild world with real rules of nature. Nobody "
                 "tells you what to become. Each moment you choose what to do next from the options your body offers, "
                 "or pick your own idea. New things are found by experimenting; nature decides what works. "
                 "Answer with one letter only.")


def choice_messages(world, a: Agent, options: List[Dict[str, Any]], own_idea: bool = False) -> List[Dict[str, str]]:
    """Choose mode (JEV-style): the model reads the scene and picks one of a few drafted plans by letter. One output
    token instead of ~90: on the RTX 3090 a decision took 6 s instead of 25 s. The system prompt is the same for
    every chit, so servers can reuse it from their prompt cache."""
    from ..sim.actions import describe_step

    rows = [f"{LETTERS[i]}) {o['goal']}: " + "; ".join(describe_step(s) for s in o["steps"][:6]) for i, o in enumerate(options)]
    if own_idea:
        rows.append(f"{LETTERS[len(options)]}) {OWN_IDEA}")
    head = f"You are {a.name}. Your nature: {a.personality()}.\n"
    return [{"role": "system", "content": CHOICE_SYSTEM},
            {"role": "user", "content": head + choice_scene(world, a) + "\n\nYOUR BODY RIGHT NOW: " + body_line(world, a)
             + "\n\nYOUR OPTIONS:\n" + "\n".join(rows) + "\n\nAnswer with one letter only."}]


FOOD_REFLEXES = ("eat", "harvest", "gather", "pickup")  # the steps a hunger reflex runs


def body_line(world, a: Agent) -> str:
    """The chit's needs in words, just before its options. The choice scene shows them as numbers ("Hunger 4 energy
    66 ..."), and "hunger" counts fullness: on a bench of 216 of the game's own choices (tools/decbench.py), Gemma 4
    12B, JevK5 4B and Ornith 35B all chose about at chance when the answer was plain (a chit at hunger 4 with food in
    hand picked "experiment" at 96%). With this line they chose to eat or sleep 99-100% of the time."""
    # a body reflex already seeing to it (the mind asks for the next plan while the reflex runs): say so, not "now",
    # or the model chose the same meal again and it was eaten after the reflex had fed the chit (Codex, #89)
    reflex = (a.plan[0].get("do") if a.plan and a.plan[0].get("_reflex") else None)
    words = []
    if a.hunger < 15:
        then = " You are already getting food." if reflex in FOOD_REFLEXES else " Eat now."
        words.append(f"You are starving: your belly is nearly empty (fullness {a.hunger:.0f} of 100).{then}")
    elif a.hunger < 45:
        words.append(f"You are hungry (fullness {a.hunger:.0f} of 100).")
    if a.energy < 15:
        night = ", and it is night" if world.is_night else ""
        then = " You are already going to sleep." if reflex == "sleep" else " Sleep now."
        words.append(f"You are exhausted (energy {a.energy:.0f} of 100){night}.{then}")
    elif a.energy < 35:
        words.append(f"You are tired (energy {a.energy:.0f} of 100).")
    if a.warmth < 15:
        words.append(f"You are freezing (warmth {a.warmth:.0f} of 100).")
    if a.health < 30:
        words.append(f"You are badly hurt (health {a.health:.0f} of 100).")
    return " ".join(words) or "Your body is fine: no urgent needs."


def messages(world, a: Agent, style: str = "full") -> List[Dict[str, str]]:
    if style == "compact":
        return [{"role": "system", "content": compact_system_prompt(world, a)},
                {"role": "user", "content": compact_scene(world, a)}]
    return [{"role": "system", "content": system_prompt(world, a)}, {"role": "user", "content": scene(world, a)}]


def with_repair(msgs: List[Dict[str, str]], rep: Dict[str, Any]) -> List[Dict[str, str]]:
    """Bounded action repair (research plan item 40): the simulator's exact reason, added to the scene (not as a second
    user turn, which some chat templates refuse). Nothing judges the plan: the model decides what to do about it."""
    note = f'\n\nYOUR PLAN FAILED: "{rep["failed"]}" could not be done: {rep["reason"]}.'
    if rep.get("dropped"):
        note += " The rest of that plan was dropped: " + "; ".join(rep["dropped"]) + "."
    note += " Reply with a plan that can work from here."
    out = [dict(m) for m in msgs]
    out[-1]["content"] = out[-1]["content"] + note
    return out


def _does(inv) -> str:
    """": what an invention does, with its strength" (the models saw the purpose and never how good the thing was)."""
    from ..sim.invent import effect_words

    words = effect_words(inv.get("effect"))
    return ": " + ", ".join(words) if words else ""


def _worn(a: Agent, k: str, world=None) -> str:
    """" (worn)" on a metal tool past half its life, so a model knows to mend it (issue #5)."""
    from ..sim.actions import METAL_OF, metal_of, tool_wear_limit

    metal = k in METAL_OF or (world is not None and metal_of(world, k))  # (an invented metal tool too, F34)
    return " (worn)" if metal and a.tool_wear.get(k, 0) >= tool_wear_limit(k, world) // 2 else ""


_FORBIDDEN = {"say": "say", "teach": "teach", "write": "write", "preach": "say"}


_REFLEX = ("warm_up", "wander")  # the simulator's own reflexes: never something to ask a model for


def compact_system_prompt(world, a: Agent) -> str:
    """A short system prompt for small or short-context models: same reply contract, one-line verb list."""
    from ..sim.actions import VERBS

    verbs = [v for v in VERBS if not (v in _FORBIDDEN and not world.flags.get(_FORBIDDEN[v])) and v not in _REFLEX]
    talk = "" if world.flags.get("say") else " You cannot talk, teach or write: learn by watching and studying."
    return (f"You are a small creature (a chit) in a wild world with real rules of nature. You decide what to do.{talk}\n"
            "Nothing is given: discover new items by EXPERIMENTING with 1-5 carried items (sometimes at a station: fire, "
            "kiln, furnace, workshop, forge, factory, mill or loom). Item properties are clues. Tools matter. Winter is cold and nothing grows.\n"
            "You can also INVENT a new thing from 2-4 carried items (give it a name and a purpose): what its parts can do "
            "decides what it can be, and the purpose chooses among that.\n"
            'Reply with ONE JSON object only: {"thought":"...","goal":"...","plan":[{"do":"gather","what":"wood","qty":4},...]}\n'
            "The plan has 2-6 steps. Step fields: do, what, qty, with (list), at, to, target, site, near, dir, text, name, purpose, "
            "give and get (trade), intent (sail).\n"
            "Verbs: " + ", ".join(verbs) + f"\nYou are {a.name}.")


def compact_scene(world, a: Agent) -> str:
    t = world.tick
    c = world.clock()
    hh = int(c["hour"])
    L: List[str] = [f"Day {c['day']} {c['season']} {hh:02d}h{' night' if c['night'] else ''}. You: {a.name} at ({a.x},{a.y})."]
    L.append(f"Hunger {a.hunger:.0f} energy {a.energy:.0f} warmth {a.warmth:.0f} health {a.health:.0f} (of 100).")
    inv = ", ".join(f"{n} {world.item_name(k)}{_worn(a, k, world)}" for k, n in sorted(a.inventory.items())) or "nothing"
    L.append(f"Carrying ({a.load()}/{a.capacity()}): {inv}{' FULL' if a.free_space() <= 0 else ''}.")
    rec = [world.item_name(k.split(':', 1)[1]) for k in a.knows if k.startswith("recipe:")]
    des = [DESIGNS[k.split(':', 1)[1]].name for k in a.knows if k.startswith("design:")]
    L.append("Can make: " + (", ".join(rec) or "nothing yet (experiment!)") + ". Can build: " + (", ".join(des) or "nothing") + ".")
    mems = a.recall(4, keywords=[a.goal] if a.goal else None, now=t)
    if mems:
        L.append("Remember: " + " | ".join(m.text[:90] for m in mems))
    res = []
    for kind in ("berries", "wood", "stone", "fiber", "clay", "sand", "ore", "iron_ore", "fish"):
        p = world.nearest_resource(a.x, a.y, kind, SIGHT)
        if p:
            res.append(f"{world.item_name(kind)} {_where(a, *p)}")
    L.append("Near: " + ("; ".join(res) or "no resources"))
    others = world.agents_near(a.x, a.y, SIGHT, exclude=a.id)[:4]
    if others:
        L.append("Chits: " + "; ".join(f"{o.name} {_where(a, o.x, o.y)} {o.activity}" for o in others))
    sts = world.structures_near(a.x, a.y, SIGHT + 4)[:5]
    if sts:
        bits = []
        for s in sts:
            d = DESIGNS[s.design]
            if not s.complete:
                bits.append(f"{d.name} site {s.id} needs " + (", ".join(f"{n} {world.item_name(k)}" for k, n in s.needs.items()) or "work"))
            else:
                bits.append(f"{d.name} {s.id}{' (ruin)' if s.ruined else ''}{' (your home)' if s.id == a.home else ''}")
        L.append("Structures: " + "; ".join(bits))
    if a.last_result:
        L.append("Last: " + a.last_result[:160])
        if loop_line(world, a):
            L.append(loop_line(world, a))
    L.append("Reply with the JSON plan.")
    out = "\n".join(l[:260] for l in L)
    if len(out) > 1790:
        out = out[:1760].rsplit("\n", 1)[0] + "\nReply with the JSON plan."
    return out


STALE_DAYS = 4


def untried_pairs(world, a: Agent, n: int = 3) -> List[str]:
    """A few combinations of handled things the chit has never tried, different for each chit and day: a pair,
    something at a nearby fire or kiln, or three things including something crafted. Models only ever mixed two
    different raw materials (stone + wood, over and over), never two of the same, never one thing in a kiln (a
    clay pot) or three (a stone axe), so World A went 20 days without a discovery. This says what hasn't been
    tried, never what will work."""
    stocked = {k for p in world.structures_near(a.x, a.y, 25, "stockpile") if p.functional
               for k, n in p.storage.items() if n > 0}
    # what's in the stockpiles counts: World B had ore in store but no chit had ever handled it, so "ore" never
    # appeared in any suggestion
    fam = [k for k in sorted(set(a.familiar) | stocked) if world.item(k) and not world.item(k).tool]
    if len(fam) < 2:
        return []
    # a combination that failed at a fire or kiln also failed without one (a no-station recipe works anywhere)
    failed = set(a.failed_experiments) | set(world.village_failed(a))
    tried = failed | {f.split(" at the ")[0] for f in failed}
    known = {k.split(":", 1)[1] for k in a.knows if k.startswith("recipe:")}
    made = [k for k in fam if k in known]
    stations = [st for st in STATIONS if world.nearest_station(a.x, a.y, st, STATION_REACH)]  # (a forge was never mentioned)
    rng = random.Random(zlib.crc32(f"{a.id}:{world.tick // 240}".encode()))
    name = world.item_name

    def key(bag, station=None):
        combo = " + ".join(f"{bag.count(k)} {name(k)}" if bag.count(k) > 1 else name(k) for k in sorted(set(bag)))
        return combo + (f" at the {station}" if station else "")

    def show(bag, station=None):
        return " + ".join(name(k) for k in bag) + (f" at the {station}" if station else "")

    pairs = [[x, y] for i, x in enumerate(fam) for y in fam[i:] if x not in known or y not in known]
    at_station = [([k], st) for st in stations for k in fam] + [([x, y], st) for st in stations for x, y in pairs]
    triples = [[c, x, y] for c in made for i, x in enumerate(fam) for y in fam[i:] if c not in (x, y)]
    # the toolmaker's intuition instinct already has, from properties the chit has seen: something long and sturdy,
    # something hard or sharp, something binding. World A's model never tried one in 20 days (its suggestions were
    # seeds + wood and cord + grain + seeds) while it had handled cord, stone and wood.
    props = {k: set(world.item(k).props) for k in fam}
    handle = [k for k in fam if props[k] & {"sturdy", "long"}]
    head = [k for k in fam if props[k] & {"hard", "sharp"}]
    bind = [k for k in fam if props[k] & {"binding", "strong"}]
    tools = [[h, x, b] for h in handle for x in head for b in bind if len({h, x, b}) == 3]
    groups = [[(b, None) for b in pairs], at_station, [(b, None) for b in triples]]
    for g in groups:
        rng.shuffle(g)
    if "furnace" in stations:  # something that burns very hot + something that melts in great heat
        fuel = [k for k in fam if "burns very hot" in props[k]]
        melt = [k for k in fam if "melts in great heat" in props[k]]
        hot = [([f, m], "furnace") for f in fuel for m in melt]
        rng.shuffle(hot)
        groups[1] = hot + groups[1]
    if tools:
        rng.shuffle(tools)
        groups[2] = [(sorted(t), None) for t in tools] + groups[2]
    out, seen = [], set()
    while len(out) < n and any(groups):
        for g in groups:
            while g:
                bag, st = g.pop()
                k = key(bag, st)
                if k not in tried and k not in seen:
                    seen.add(k)
                    out.append(show(bag, st))
                    break
            if len(out) == n:
                break
    return out


def stale_days(world) -> int:
    """Whole days since anything was first made, discovered or built in this world (0 if something was today)."""
    last = max((f.get("tick", 0) for f in getattr(world, "first", {}).values()), default=0)
    return (world.tick - last) // 240


LAW_DAYS = 10  # how long a decree outlives its chief's time in charge


def laws_in_force(world) -> List[Dict[str, Any]]:
    """The current chief's laws, and anyone's from the last LAW_DAYS days. World A obeyed a dead chief's
    "secure seeds for every plot before building" for 20 days and stopped discovering anything."""
    now, leader = world.tick, getattr(world, "leader", "")
    return [law for law in getattr(world, "laws", [])
            if law.get("by") == leader or now - law.get("tick", 0) < LAW_DAYS * 240]


def beliefs_around(world, a: Agent) -> List[Dict[str, Any]]:
    """The beliefs a chit could know about: its neighbours' where chits can talk, otherwise only the ones shown by
    shrines it can see (a chit can't be told what anyone believes). Most followed first."""
    beliefs = getattr(world, "beliefs", {})
    if not beliefs:
        return []
    # Only faiths the chit has met: preached to it, a shrine it can see, or a close friend's. Listing every
    # neighbour's made everyone join on day 1, so preaching and prayer never converted anyone.
    ids = world.known_beliefs(a) if hasattr(world, "known_beliefs") else set()
    return sorted((beliefs[b] for b in ids if b in beliefs), key=lambda b: -len(b["followers"]))[:5]


def reflection_messages(world, a: Agent) -> List[Dict[str, str]]:
    mems = sorted(a.memories, key=lambda m: (-m.importance, -m.tick))[:18]
    mems.sort(key=lambda m: m.tick)
    body = "\n".join(f"- [m{m.id}] day {m.tick // 240 + 1}: {m.text}" for m in mems)
    prev = "\n".join(f"- {l}" for l in a.lessons) or "(none yet)"
    amb = (f'Your ambition is: "{a.ambition}". You may keep it or choose a new one.' if a.ambition
           else "You have no ambition yet. You may choose one.")
    chief = ("\nYou are the chief. If you believe a rule for everyone is needed, you may add \"decree\": \"...\" — "
             "in your own words; leave it out otherwise." if getattr(world, "leader", "") == a.id and world.flags.get("say") else "")
    if chief and hasattr(world, "civic"):
        from ..sim import projects

        now = projects.scene_line(world, a)
        ideas = projects.ideas(world)
        if ideas:
            chief += ("\nYou may also set the village's next project, one thing everyone works towards together: add "
                      f"\"project\": \"...\" (for example {' or '.join(chr(34) + i + chr(34) for i in ideas)}). "
                      + (f"Now: {now}" if now else "There is no village project now."))
    bel = getattr(world, "beliefs", {}).get(a.belief)
    around = beliefs_around(world, a)
    if bel:
        faith = f'You follow {bel["name"]}: "{bel["tenet"]}". If you name a belief, name this one.'
    elif around:
        listed = "\n".join(f'- {b["name"]} (founded by {b["founder_name"]}, {len(b["followers"])} '
                           f'follower{"s" if len(b["followers"]) != 1 else ""}): "{b["tenet"]}"' for b in around)
        faith = ("Beliefs held around you:\n" + listed + "\nIf one of these speaks to you, you may join it: add "
                 '"belief": {"name": "<its name>"}. Only if none of them fits and you truly hold a different '
                 'conviction, found your own: "belief": {"name": "...", "tenet": "..."}. New faiths are rare; '
                 "do not add one just to fill the field.")
    else:
        faith = ('If, from your life so far, you truly hold a conviction about the world, what is sacred, or how to '
                 'live, you may add "belief": {"name": "...", "tenet": "one short sentence"}. Do not invent one just to fill the field.')
    return [
        {"role": "system", "content": f"You are {a.name}, a chit, reflecting quietly at the end of the week. "
         "Draw up to 3 short, practical lessons from your experiences — things that will help you survive, build and "
         "discover. Only state lessons supported by the memories, and cite the memories each one comes from. "
         "Also name your ambition: a life goal, ambitious but possible in this world, in one short sentence. "
         "Reply as JSON: {\"lessons\":[{\"text\":\"...\",\"from\":[12,15]}],\"ambition\":\"...\"}"},
        {"role": "user", "content": f"Your lessons so far:\n{prev}\n\n{amb}\n{faith}{chief}\n\nYour notable memories:\n{body}\n\nWhat have you learned?"},
    ]
