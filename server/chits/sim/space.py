"""The space programme (world.SPACE_PROGRAMME): after the first launch, a launch pad keeps a late world busy.

The pad's completion is the first launch (World._launch). With the programme, its crew and builders saw how the
rocket was put together, and a rocket assembled at the pad (rocket sections and fuel) can be flown again: each launch
after the first does the next mission on the ladder. A satellite and then a station in orbit make study go further
island-wide, the Moon landing is a wonder everyone remembers, and after the station every launch is an expedition.
State is world.space: {"launches": n, "satellites": n, "moon": tick|None, "station": tick|None}, saved only when
not empty."""

from typing import Any, Dict, List, Optional

from .agent import TICKS_PER_DAY, Agent

SAT_STUDY = 1.25  # study goes this much further island-wide with a satellite up (and as much again with a station)
STATION_STUDY = 1.25
MOON_MOOD = 20.0  # everyone's lift on the day of the Moon landing
STATION_MOOD = 2.0  # ...and each day there is a station in orbit
EXPEDITION_MOOD = 5.0
CREW = 3  # the launcher and up to two grown-ups standing by
CREW_REACH = 6
MISSIONS = ("satellite", "moon", "station")  # the 2nd, 3rd and 4th launch; after that, expeditions
WHERE = ("round the far side of the Moon", "out to the red planet", "past the ringed giant",
         "to the comet's tail", "far beyond the last bright planet")


def on() -> bool:
    from . import world as W

    return bool(W.SPACE_PROGRAMME)


def launches(world) -> int:
    """How many rockets this world has flown (the pad's completion counts: an older save's first launch too)."""
    sp = getattr(world, "space", None) or {}
    return int(sp.get("launches") or (1 if "design:launch_pad" in world.first else 0))


def next_mission(world) -> str:
    n = launches(world)
    return MISSIONS[n - 1] if 1 <= n <= len(MISSIONS) else "expedition" if n > len(MISSIONS) else ""


def first_launch(world, s) -> None:
    """The pad stood and its rocket flew (World._launch): its crew and builders saw how a rocket goes together."""
    if not on():
        return
    sp = world.space
    sp["launches"] = max(1, int(sp.get("launches") or 0))
    _teach(world, s)


def _teach(world, s) -> int:
    n = 0
    for aid in s.builders:
        a = world.agents.get(aid)
        if a is not None and a.learn("recipe:rocket", "observed", world.tick):
            a.remember(world.tick, "The rocket that flew showed me how one goes together, at the launch pad", 4, "discovery")
            n += 1
    return n


def knows_rocket(world, members: Optional[List[Agent]] = None) -> bool:
    return any(a.knows_recipe("rocket") for a in (members if members is not None else world.agents.values()))


def pads(world) -> List:
    return [s for s in world.structures.values() if s.design == "launch_pad" and s.functional]


def crew_for(world, a: Agent, pad) -> List[Agent]:
    cx, cy = pad.center()
    others = [o for o in world.agents_near(int(cx), int(cy), CREW_REACH, exclude=a.id) if not o.is_child(world.tick)]
    return [a] + others[: CREW - 1]


def launch(world, a: Agent, pad) -> Dict[str, Any]:
    """A rocket flies from `pad` with `a` aboard: the next mission on the ladder. Returns what it did."""
    from .world import _join_names

    sp = world.space
    n = launches(world) + 1
    sp["launches"] = n
    crew = crew_for(world, a, pad)
    names = _join_names([c.name for c in crew])
    mission = MISSIONS[n - 2] if n - 2 < len(MISSIONS) else "expedition"
    for c in crew:
        c.astronaut = True
        c.bump("launches")
    t = world.tick
    if mission == "satellite":
        sp["satellites"] = int(sp.get("satellites") or 0) + 1
        text, imp = f"{names} set the first satellite circling {world.name} — study goes further now, all over the island", 4
        mem = "We set a satellite circling the island"
    elif mission == "moon":
        sp["moon"] = t
        text, imp = f"{names} walked on the Moon — the whole island watched", 5
        mem = "I walked on the Moon"
        for o in world.agents.values():
            o.mood = min(100.0, o.mood + MOON_MOOD)
            if o not in crew:
                o.remember(t, f"The day {names} walked on the Moon: the whole island watched", 5, "wonder")
    elif mission == "station":
        sp["station"] = t
        text, imp = f"{names} raised a station in orbit high above {world.name}", 5
        mem = "We built a station in orbit"
    else:
        k = n - 1 - len(MISSIONS)
        where = WHERE[(k - 1) % len(WHERE)]
        sp["expeditions"] = k
        text, imp = f"{names} flew expedition {k} {where}", 3
        mem = f"I flew {where}"
        for o in world.agents.values():
            o.mood = min(100.0, o.mood + EXPEDITION_MOOD)
    for c in crew:
        c.remember(t, mem, 5, "wonder")
    cx, cy = pad.center()
    world.emit("space", text, imp, a.id, cx, cy, mission=mission, launch=n, crew=[c.id for c in crew], structure=pad.id)
    return {"mission": mission, "launch": n, "crew": [c.id for c in crew], "text": text}


def study_mult(world) -> float:
    """What the programme in orbit does for study: a satellite, then a station, each a quarter more."""
    sp = getattr(world, "space", None) or {}
    if not on() or not sp:
        return 1.0
    return (SAT_STUDY if sp.get("satellites") else 1.0) * (STATION_STUDY if sp.get("station") is not None else 1.0)


def daily(world) -> None:
    """Each day: a station in orbit lifts everyone a little. (An older save whose pad stood before the programme:
    its builders still know how the rocket went together.)"""
    if not on():
        return
    sp = world.space
    if not sp and "design:launch_pad" in world.first:
        for s in pads(world):
            sp["launches"] = 1
            if not _teach(world, s) and not knows_rocket(world):  # (its builders long dead: those living by it work it out)
                cx, cy = s.center()
                for a in [o for o in world.agents_near(int(cx), int(cy), 12) if not o.is_child(world.tick)][:CREW]:
                    a.learn("recipe:rocket", "inspected", world.tick)
    if sp.get("station") is not None:
        for o in world.agents.values():
            o.mood = min(100.0, o.mood + STATION_MOOD)


def view(world) -> Optional[Dict[str, Any]]:
    """The programme for the observer: launches so far, what is up there, and the next mission."""
    sp = getattr(world, "space", None) or {}
    if not on() or not sp:
        return None
    day = lambda t: t // TICKS_PER_DAY + 1 if t is not None else None
    return {"launches": launches(world), "satellites": int(sp.get("satellites") or 0), "moon_day": day(sp.get("moon")),
            "station_day": day(sp.get("station")), "expeditions": int(sp.get("expeditions") or 0),
            "next": next_mission(world), "rockets": sum(o.inventory.get("rocket", 0) for o in world.agents.values())
            + sum(s.storage.get("rocket", 0) for s in world.structures.values())}
