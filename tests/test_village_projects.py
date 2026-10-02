"""Village projects, research at libraries, and wants and renown (sim/projects.py, research.py, wants.py)."""

import json
import random

from chits import views
from chits.brain import civic
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.brain.mind import apply_reflection
from chits.sim import actions, projects, research, wants
from chits.sim.actions import DONE, RUNNING
from chits.sim.world import Tablet, World


def _world(culture: str = "direct", n: int = 6) -> World:
    w = World("A", "A", 3, culture, 64, n)
    for a in w.agents.values():
        a.hunger = a.energy = a.warmth = 95.0
    return w


def _run(w: World, a, step, limit: int = 600) -> str:
    step = dict(step)
    for _ in range(limit):
        w.tick += 1
        res = actions.advance(w, a, step)
        if res != RUNNING:
            return res
    return "timeout"


def _build(w: World, a, design: str, dx: int = 3):
    pos = w.find_site(design, a.x + dx, a.y, 12)
    st = w.place_site(design, pos[0], pos[1], a)
    st.needs = {}
    w.complete_structure(st, a)
    return st


def _events(w: World, kind: str):
    return [e for e in w.events if e.kind == kind]


# ---------------------------------------------------------------------------------------------- projects
def test_the_village_picks_the_next_ages_first_step_by_need_or_by_its_chief():
    w = _world()
    a = next(iter(w.agents.values()))
    w.first["design:campfire"] = {"tick": 1, "by": a.id, "name": a.name}  # Firekeepers: a stone axe is next
    w.leader = ""
    p = projects.pick(w)
    # a stone axe needs cord and a sharp stone, which nobody can make yet: the first of them is the project
    assert (p["kind"], p["key"], p["chosen_by"]) == ("discover", "cord", "need")
    w.civic["project"] = None
    w.leader = a.id
    p = projects.pick(w)
    # with a chief too: the world's own pick is never announced as anyone's call (a model chief names one itself)
    assert p["chosen_by"] == "need" and p["by"] == ""
    ev = _events(w, "project")[-1]
    assert ev.importance >= 4 and "turned to a new project" in ev.text and a.name not in ev.text
    assert "your call" not in projects.scene_line(w, a)
    # chits hear what the thing is like, never its name or how it's made
    line = projects.scene_line(w, next(o for o in w.agents.values() if o is not a))
    assert line.startswith("Village project: discover something strong, binding and flexible") and "chosen by need" in line
    assert "cord" not in line and "fiber" not in line
    assert "Village project:" in P.scene(w, a)
    # a structure the village lacks is a project too, once someone knows how to build it
    w.agents[a.id].learn("recipe:cord", "discovered", w.tick)
    w.agents[a.id].learn("design:stockpile", "insight", w.tick)
    assert ("build", "stockpile") in {(c[1], c[2]) for c in projects.candidates(w)}


def _iron_age(w: World):
    """World B's live state: Iron Age, iron made once, the forge known but never built."""
    a, b = list(w.agents.values())[:2]
    w.first["recipe:iron"] = {"tick": 1, "by": a.id, "name": a.name}
    for k in ("recipe:iron", "recipe:charcoal", "recipe:brick", "recipe:pot", "recipe:cord", "design:forge"):
        a.learn(k, "discovered", w.tick)
    for d in ("kiln", "furnace", "workshop"):
        _build(w, a, d)
    pile = _build(w, a, "stockpile", dx=-3)
    pile.storage = {"brick": 3, "iron": 1}
    return a, b, pile


def test_the_road_to_the_next_age_names_its_blocker():
    w = _world()
    _iron_age(w)
    r = projects.road(w)
    assert r["age"] == "Machine Age" and r["text"].startswith("Machine Age: ")
    names = [s["name"] for s in r["steps"]]
    for done in ("iron", "charcoal", "brick"):
        assert next(s for s in r["steps"] if s["name"] == done)["done"]
    forge = next(s for s in r["steps"] if s["name"] == "forge")
    assert not forge["done"] and forge["needs"] == "needs 7 more brick, 3 more iron"
    assert names.index("forge") < names.index("steel") < names.index("gear") < names.index("steam engine") == len(names) - 1
    assert "forge ✗ (needs 7 more brick, 3 more iron) · steel ✗ · gear ✗" in r["text"]
    assert views.progress(w, [])["road"]["text"] == r["text"]


def test_a_project_makes_enough_of_a_material_before_the_building():
    w = _world()
    a, b, pile = _iron_age(w)
    pile.storage["brick"] = 10
    w.leader = ""
    p = projects.pick(w)
    assert (p["kind"], p["key"], p["n"], p["for"]) == ("make", "iron", 4, "forge")
    assert projects.scene_line(w, b).startswith("Village project: make 4 iron for a forge (chosen by need) — the village has 1 of 4")
    # who knows how makes it and stores it; who doesn't fetches what it's made of
    plan = civic.make_plan(w, a, p)
    assert plan["steps"][-2]["do"] in ("craft", "work") and plan["steps"][-2]["what"] == "iron"
    assert plan["steps"][-1] == {"do": "store", "what": "iron"}
    b.inventory["stone_pick"] = 1
    assert civic.make_plan(w, b, p)["steps"] == [{"do": "gather", "what": "iron_ore", "qty": 4},
                                                {"do": "store", "what": "iron_ore"}]
    pile.storage["iron"] = 4
    w.tick = 10
    projects.tick(w)
    assert "4 iron are ready for the forge" in _events(w, "project_done")[-1].text
    nxt = w.civic["project"]
    assert (nxt["kind"], nxt["key"]) == ("build", "forge")


def test_a_building_project_tracks_its_site_and_completes_as_a_big_event():
    w = _world()
    a, b = list(w.agents.values())[:2]
    for c in (a, b):
        c.learn("design:kiln", "insight", w.tick)
    w.leader = a.id
    p = projects.start(w, "build", "kiln", "the village has none", a, "chief")
    assert "no site yet" in projects.scene_line(w, b)
    pos = w.find_site("kiln", a.x + 3, a.y, 12)
    site = w.place_site("kiln", pos[0], pos[1], a)
    site.needs["clay"] -= 4
    site.builders = {a.id: 4.0}
    w.tick = 10
    projects.tick(w)
    assert p["site"] == site.id and a.id in projects.helpers(w, p)
    line = projects.scene_line(w, b)
    assert f"site {site.id}" in line and "needs 4 more clay, 4 more stone" in line and "1 chit helping" in line
    site.needs, site.builders[b.id] = {}, 10.0
    before = (a.renown, b.renown)
    w.complete_structure(site, b)
    w.tick = 20
    projects.tick(w)
    done = _events(w, "project_done")
    assert done and done[-1].importance == 5 and "built the kiln" in done[-1].text
    assert w.civic["done"][-1]["key"] == "kiln"
    assert a.renown > before[0] and b.renown > before[1] + 1  # b did most of the work
    assert (w.civic.get("project") or {}).get("key") != "kiln"  # a new project is picked straight away (if any)


def test_a_discovery_project_counts_attempts_and_ends_with_the_discovery():
    w = _world()
    a = next(iter(w.agents.values()))
    p = projects.start(w, "discover", "cord", "test", None, "need")
    a.bump("experiments", 3)
    w.tick = 10
    projects.tick(w)
    assert p["attempts"] == 3 and a.id in projects.helpers(w, p)
    a.inventory = {"fiber": 2}
    assert _run(w, a, {"do": "experiment", "with": ["fiber", "fiber"]}) == DONE
    assert a.knows_recipe("cord")
    w.tick = (w.tick // 10 + 1) * 10
    projects.tick(w)
    done = _events(w, "project_done")
    assert done and f"{a.name} discovered how to make cord" in done[-1].text
    assert a.renown >= 6  # the discovery, and the village's thanks


def test_a_project_can_be_to_find_what_nobody_has_handled():
    w = _world()
    a, b = list(w.agents.values())[:2]
    w.first["recipe:clay_tablet"] = {"tick": 1, "by": a.id, "name": a.name}  # Scribes: copper is next
    for k in ("recipe:charcoal", "recipe:brick"):
        a.learn(k, "discovered", w.tick)
    _build(w, a, "kiln")
    w.leader = ""
    p = projects.pick(w)
    # copper needs a furnace, and only someone who knows bricks and has held copper ore can imagine one
    assert (p["kind"], p["key"], p["for"]) == ("find", "ore", "furnace")
    line = projects.scene_line(w, b)
    assert line.startswith("Village project: find something heavy with metallic streaks that melts in great heat")
    assert "ore" not in line.split(" — ")[0].replace("more", "")
    assert "furnace ✗ (nobody has handled copper ore yet; needs 6 more brick)" in projects.road(w)["text"]
    plan = civic.find_plan(w, a, p, random.Random(2))
    assert not any(s.get("what") == "ore" for s in plan["steps"])  # no pick: it can't get any
    a.inventory["stone_pick"] = 1
    plan = civic.find_plan(w, a, p, random.Random(2))
    assert plan["steps"][0]["do"] in ("explore", "gather", "take")
    # what the village needs isn't known, only what it is like: the plan doesn't depend on which thing it is
    other = dict(p, key="sand")
    assert civic.find_plan(w, a, other, random.Random(2)) == plan
    a.add("ore", 1)
    w.notice_items(a)
    assert a.knows_design("furnace")
    w.tick = 10
    projects.tick(w)
    assert f"{a.name} found copper ore" in _events(w, "project_done")[-1].text
    nxt = w.civic["project"]
    assert (nxt["kind"], nxt["key"], nxt["for"]) == ("make", "brick", "furnace")


def test_instinct_offers_to_help_the_project():
    w = _world()
    a = next(iter(w.agents.values()))
    a.learn("design:kiln", "insight", w.tick)
    p = projects.start(w, "build", "kiln", "test", None, "need")
    site = w.place_site("kiln", *w.find_site("kiln", a.x + 2, a.y, 12), a)
    w.tick = 10
    projects.tick(w)
    a.inventory = {"clay": 4}
    opts = civic.project_options(Instinct(), w, a, random.Random(1))
    assert opts, "a chit that can bring clay is offered the village's kiln"
    weight, plan = opts[0]
    assert weight >= civic.PROJECT_W and plan["steps"][-1] == {"do": "help", "site": site.id, "_proj": p["id"]}
    a.plan = plan["steps"]
    assert a.id in projects.helpers(w, p)
    # and instinct's own planner draws it
    ins = Instinct()
    ins._world = w
    drawn = [ins._progress(w, a, random.Random(i)) for i in range(30)]
    assert any(s.get("_proj") == p["id"] for d in drawn for s in d["steps"])


class _Fixed(random.Random):
    def __init__(self, v: float):
        super().__init__(1)
        self.v = v

    def random(self) -> float:
        return self.v


def test_the_project_comes_before_idle_talk_some_of_the_time():
    w = _world()
    a = next(iter(w.agents.values()))
    a.familiar |= {"fiber", "wood", "stone"}
    p = projects.start(w, "discover", "cord", "test", None, "need")
    ins = Instinct()
    ins._world = w
    plan = ins._communal(w, a, _Fixed(0.0))
    assert plan and plan["goal"] == "experiment for the village's discovery"
    assert all(s.get("_proj") == p["id"] for s in plan["steps"])
    assert civic.duty(ins, w, a, _Fixed(0.99)) is None  # not every time


def test_the_world_runs_the_village_each_day_and_tick():
    w = _world()
    a = next(iter(w.agents.values()))
    for _ in range(240):
        w.step()
    p = w.civic["project"]
    assert p and p["kind"] == "build" and p["key"] == "campfire"  # a village with no fire: the Firekeepers are next
    assert all(o.want for o in w.agents.values() if not o.is_child(w.tick))
    a.bump("experiments", 2)
    start = projects.start(w, "discover", "cord", "test", None, "need")
    a.bump("experiments", 2)
    for _ in range(10):
        w.step()
    assert start["attempts"] == 2


def test_a_chief_can_name_the_project_in_its_reflection():
    w = _world()
    a, b = list(w.agents.values())[:2]
    a.learn("design:kiln", "insight", w.tick)
    w.leader = a.id
    msgs = P.reflection_messages(w, a)
    assert '"project"' in msgs[1]["content"] and "build a kiln" in msgs[1]["content"]
    apply_reflection(w, b, json.dumps({"lessons": [], "project": "build a kiln"}))
    assert (w.civic.get("project") or {}).get("key") != "kiln" or w.civic["project"]["chosen_by"] != "chief"
    apply_reflection(w, a, json.dumps({"lessons": [], "project": "a spaceship"}))  # not something the village can do
    apply_reflection(w, a, json.dumps({"lessons": [], "project": "Build a kiln!"}))
    p = w.civic["project"]
    assert (p["kind"], p["key"], p["chosen_by"], p["by"]) == ("build", "kiln", "chief", a.id)


def test_projects_are_in_the_api_and_survive_a_restart():
    w = _world()
    a = next(iter(w.agents.values()))
    projects.start(w, "discover", "cord", "test", a, "chief")
    a.want = {"kind": "first", "key": "", "text": "to be the first to discover something", "since": 0}
    a.renown = 7.5
    pv = views.progress(w, [])["project"]["active"]
    assert pv["title"] == "discover how to make cord" and pv["by"] == a.name and 0 <= pv["progress"] <= 1
    d = views.agent_detail(w, a)
    assert d["want"] == "to be the first to discover something" and d["renown"] == 7.5 and d["famous"]
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.civic["project"]["key"] == "cord" and w2.agents[a.id].renown == 7.5
    assert w2.agents[a.id].want["text"] == a.want["text"]


# ---------------------------------------------------------------------------------------------- research
def _library(w: World, a, tablets: int = 3):
    lib = _build(w, a, "library")
    for i in range(tablets):
        t = Tablet(f"t{i}", "recipe:cord", a.id, a.name, 0, lib.x, lib.y, lib.id, "2 plant fiber -> cord")
        w.tablets[t.id] = t
        lib.shelf.append(t.id)
    return lib


def test_study_is_a_verb_of_its_own():
    assert actions.normalize_verb("study") == "study" and actions.normalize_verb("research") == "study"
    assert '"do":"study"' in P.verb_guide(_world())
    w = _world()
    a = next(iter(w.agents.values()))
    hut = _build(w, a, "hut")
    a.knows.pop("design:hut")
    # studying a thing (not a library) still means inspecting it, as "study" always did
    assert _run(w, a, {"do": "study", "target": hut.id}) == DONE and a.stats.get("studied", 0) == 0


def test_enough_study_gives_the_village_a_hint_worded_by_properties():
    w = _world()
    a = next(iter(w.agents.values()))
    _library(w, a)
    a.familiar |= {"clay", "sand"}
    sessions = 0
    while not w.civic["hints"] and sessions < 20:
        assert _run(w, a, {"do": "study"}) == DONE
        sessions += 1
    assert w.civic["hints"], "the village's scholars had an idea"
    assert sessions >= 3 and a.stats["studied"] == sessions and a.skill("scholar") > 0
    h = w.civic["hints"][0]
    assert h["recipe"] == "pot"  # the simplest thing made from what the village has handled
    assert h["text"] == "Scholars at the library think something that hardens in heat, at a kiln, might make something new."
    ev = _events(w, "hint")[-1]
    assert ev.actor == a.id and ev.importance >= 3
    other = next(o for o in w.agents.values() if o is not a)
    assert any("Scholars' hint: something that hardens in heat" in l for l in P.scene(w, other).splitlines())
    # where chits can't talk, only those who study know the scholars' ideas
    wb = _world("stigmergy")
    b = next(iter(wb.agents.values()))
    wb.civic["hints"] = [dict(h)]
    assert research.scene_lines(wb, b) == []
    b.bump("studied")
    assert research.scene_lines(wb, b)


def test_instinct_tries_the_hinted_combination():
    w = _world()
    a = next(iter(w.agents.values()))
    _build(w, a, "kiln")
    a.familiar |= {"clay", "sand", "wood"}
    a.inventory = {"clay": 1, "sand": 1}
    parts = [("hardens in heat", 1), ("melts in great heat", 1)]
    w.civic["hints"] = [{"id": "h1", "recipe": "brick", "parts": [list(x) for x in parts], "station": "kiln",
                         "text": research.hint_text(parts, "kiln"), "tick": 0, "found": 0}]
    plan = civic.hinted_experiment(Instinct(), w, a, random.Random(4))
    assert plan and plan["steps"][-1] == {"do": "experiment", "with": ["clay", "sand"], "at": "kiln"}
    a.failed_experiments.append("clay + sand at the kiln")
    assert civic.hinted_experiment(Instinct(), w, a, random.Random(4)) is None  # already tried: not again


# ---------------------------------------------------------------------------------------------- wants and renown
def test_every_adult_wants_something_and_a_want_can_come_true():
    w = _world()
    a = next(iter(w.agents.values()))
    projects.new_day(w)
    assert all(o.want.get("text") for o in w.agents.values() if not o.is_child(w.tick))
    assert f"You want: {a.want['text']}." in P.scene(w, a)
    a.want = {"kind": "home", "key": "brick_house", "text": "a brick house of your own", "since": w.tick}
    hut = _build(w, a, "hut")
    a.home, a.mood, a.renown = hut.id, 50.0, 0.0
    w.tick = 30
    projects.tick(w)
    assert a.want and not _events(w, "wish")  # a hut isn't a brick house
    house = _build(w, a, "brick_house", dx=-4)
    a.home = house.id
    w.tick = 60
    projects.tick(w)
    ev = _events(w, "wish")
    assert ev and ev[-1].text == f"{a.name} got what they wanted: a brick house of their own"
    assert a.mood == 70.0 and a.renown >= wants.WISH_RENOWN and a.want == {}


def test_renown_comes_from_discoveries_and_teaching():
    w = _world()
    a, b = list(w.agents.values())[:2]
    w.learned(a, "recipe:sharp_stone", "discovered")
    w.learned(b, "recipe:sharp_stone", "taught", a)
    w.tick = 10
    projects.tick(w)
    assert a.renown == 4.0 and b.renown == 0.0  # 3 for the discovery, 1 for teaching it
    projects.tick(w)
    assert a.renown == 4.0  # the same events are never counted twice


def test_chits_near_the_most_renowned_chit_imitate_what_it_does():
    w = _world()
    star, near, far = list(w.agents.values())[:3]
    star.renown, star.goal = 10.0, "explore the north"
    near.x, near.y = star.x + 2, star.y
    far.x, far.y = star.x + 40, star.y
    opts = [(1.0, {"goal": "explore", "steps": []}), (1.0, {"goal": "collect wood", "steps": []})]
    assert wants.famous(w) is star
    assert [w_ for w_, _ in civic.imitation_bias(w, near, opts)] == [civic.IMITATE_BIAS, 1.0]
    assert [w_ for w_, _ in civic.imitation_bias(w, far, opts)] == [1.0, 1.0]
    assert [w_ for w_, _ in civic.imitation_bias(w, star, opts)] == [1.0, 1.0]
    star.renown = wants.FAME_MIN - 1  # nobody stands out: nobody is imitated
    assert [w_ for w_, _ in civic.imitation_bias(w, near, opts)] == [1.0, 1.0]


# ---------------------------------------------------------------------------------------------- culture
def test_where_chits_cant_talk_only_those_who_see_the_site_know_the_project():
    """World B can't talk: a project is known by the chit that chose it and by those who can see its site go up.
    Every chit's scene used to carry it, a channel that culture doesn't have."""
    w = _world("stigmergy", n=4)
    a, b, c = list(w.agents.values())[:3]
    for x in (a, b, c):
        x.learn("design:kiln", "insight", w.tick)
    w.leader = a.id
    p = projects.start(w, "build", "kiln", "the village has none", a, "elder")
    b.x, b.y = a.x + 2, a.y
    c.x, c.y = min(w.w - 2, a.x + 30), a.y
    assert projects.knows(w, a, p) and projects.scene_line(w, a)  # its own call
    assert not projects.knows(w, b, p) and projects.scene_line(w, b) == ""  # no site yet: nothing to see
    assert "Village project" not in P.scene(w, b) and "Village project" not in P.choice_scene(w, b)
    ins = Instinct()
    assert civic.project_options(ins, w, b, random.Random(1)) == []
    pos = w.find_site("kiln", a.x + 3, a.y, 12)
    w.place_site("kiln", pos[0], pos[1], a)
    w.tick += 10
    projects.tick(w)
    assert projects.knows(w, b, p) and projects.scene_line(w, b).startswith("Village project: build a kiln")
    assert not projects.knows(w, c, p) and projects.scene_line(w, c) == ""  # too far to see it
    # where chits talk, word gets round
    d = _world("direct", n=4)
    x, y = list(d.agents.values())[:2]
    y.x = min(d.w - 2, x.x + 30)
    q = projects.start(d, "discover", "cord", "test", x, "chief")
    assert projects.knows(d, y, q) and projects.scene_line(d, y).startswith("Village project: discover")


def test_where_chits_cant_talk_they_only_want_what_they_have_seen():
    for culture, expect in (("stigmergy", False), ("direct", True)):
        w = _world(culture, n=4)
        a, b = list(w.agents.values())[:2]
        w.first["recipe:copper_axe"] = {"tick": 1, "by": b.id, "name": b.name}
        a.familiar.discard("copper_axe")
        a.inventory.pop("copper_axe", None)
        wanted = {o["key"] for _, o in wants.options(w, a) if o["kind"] == "item"}
        assert ("copper_axe" in wanted) is expect, culture
        a.familiar.add("copper_axe")  # seen one: now it can want one anywhere
        assert "copper_axe" in {o["key"] for _, o in wants.options(w, a) if o["kind"] == "item"}


def test_only_chits_that_knew_of_the_project_get_its_thanks():
    """World B (no speech): nobody was told of a discovery project, so nobody is thanked for it, or remembers
    helping with it. Where chits talk, the finder and those who tried are. (The discovery itself earns renown in
    both worlds; the village's thanks come on top of it.)"""
    gain = {}
    for culture, thanked in (("stigmergy", False), ("direct", True)):
        w = _world(culture)
        a = next(iter(w.agents.values()))
        p = projects.start(w, "discover", "cord", "test", None, "need")
        a.bump("experiments", 2)
        w.tick = 10
        projects.tick(w)
        assert (a.id in projects.helpers(w, p)) is thanked, culture
        a.inventory = {"fiber": 2}
        assert _run(w, a, {"do": "experiment", "with": ["fiber", "fiber"]}) == DONE
        before = a.renown
        w.tick = (w.tick // 10 + 1) * 10
        projects.tick(w)
        done = _events(w, "project_done")[-1]
        assert (a.id in done.data["helpers"]) is thanked, culture
        assert any("village's project is done" in m.text for m in a.memories) is thanked, culture
        gain[culture] = a.renown - before
    assert gain["direct"] - gain["stigmergy"] >= 3


def test_a_make_project_credits_the_shifts_at_a_station():
    w = _world()
    a, b, pile = _iron_age(w)
    pile.storage["brick"] = 10
    p = projects.pick(w)
    assert (p["kind"], p["key"]) == ("make", "iron")
    a.bump("produced_iron", 1)  # a shift at the furnace (sim/actions.py _do_work)
    w.tick = 10
    projects.tick(w)
    assert a.id in projects.helpers(w, p)
    pile.storage["iron"] = 4
    w.tick = 20
    projects.tick(w)
    done = _events(w, "project_done")[-1]
    assert a.id in done.data["helpers"] and f"made by {a.name}" in done.text


def test_a_chit_that_cant_make_it_only_hears_what_it_needs_where_chits_talk():
    for culture, offered in (("stigmergy", False), ("direct", True)):
        w = _world(culture)
        a, b, pile = _iron_age(w)
        p = projects.start(w, "make", "iron", "test", None, "need", {"n": 4, "for": "forge"})
        b.inventory["stone_pick"] = 1
        plan = civic.make_plan(w, b, p)
        assert (plan is not None) is offered, culture
        a.knows.pop("recipe:iron")  # and nobody who makes it to hear it from
        for o in w.agents.values():
            o.knows.pop("recipe:iron", None)
        assert civic.make_plan(w, b, p) is None
