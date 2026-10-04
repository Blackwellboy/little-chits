"""One project slot per settlement (F32). There used to be one project for the whole world, and a building was
"lacking" only while there was none anywhere: a daughter village never got a project for the kiln, workshop or
stockpile its mother had, though its chits could not use them. A project now belongs to a village; a world with one
village behaves as it always did (tests/test_village_identity.py)."""

import json
import math
import random

from chits import views
from chits.brain import civic
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim import projects, wants
from chits.sim.items import DESIGNS
from chits.sim.world import World


def _put(w: World, a, design: str, at, radius: int = 10):
    pos = w.find_site(design, at[0], at[1], radius, reach=(a.x, a.y))
    assert pos is not None, f"no room for a {design} near {at}"
    st = w.place_site(design, pos[0], pos[1], a)
    st.needs = {}
    w.complete_structure(st, a)
    return st


def _spot(w: World, a, froms, lo: int, hi: int):
    """A place to settle on the same land, between lo and hi tiles (as the crow walks) from every place in `froms`,
    with room for a few buildings."""
    cx, cy = froms[0]
    for r in range(lo, hi + 1, 2):
        for k in range(48):
            x, y = int(cx + r * math.cos(k * math.tau / 48)), int(cy + r * math.sin(k * math.tau / 48))
            if not (12 <= x < w.w - 12 and 12 <= y < w.h - 12) or not w.same_land_xy(a, x, y):
                continue
            if any(not lo <= max(abs(x - fx), abs(y - fy)) <= hi for fx, fy in froms):
                continue
            if all(w.find_site("hut", x + dx, y + dy, 2, reach=(a.x, a.y)) for dx, dy in ((0, 0), (4, 0), (0, 4))):
                return x, y
    raise AssertionError("no second site on this island")


def _settle(w: World, chits, at):
    """These chits live here: two huts and a fire close together (a settlement, as the world finds them)."""
    for c in chits:
        c.x, c.y = at
    huts = [_put(w, chits[0], "hut", (at[0] + dx, at[1]), 4) for dx in (0, 4)]
    _put(w, chits[0], "campfire", (at[0], at[1] + 4), 4)
    for i, c in enumerate(chits):
        c.home = huts[i % 2].id
    return huts


def _two(culture: str = "direct", n: int = 12, hamlet: int = 0, far: int = 50):
    """Two villages `far`+ tiles apart on one island (the mother's chits, the daughter's chits), and with `hamlet`
    a third settlement of that many chits, too small to carry a project."""
    w = World("A", "A", 3, culture, 128, n)
    ags = list(w.agents.values())
    for a in ags:
        a.hunger = a.energy = a.warmth = a.health = 95.0
    w.leader = ""
    home = (ags[0].x, ags[0].y)
    there = _spot(w, ags[0], [home], far, far + 14)
    rest = ags[:len(ags) - hamlet]
    A, B = rest[:len(rest) // 2], rest[len(rest) // 2:]
    _settle(w, A, home)
    _settle(w, B, there)
    H = ags[len(ags) - hamlet:]
    if H:
        _settle(w, H, _spot(w, ags[0], [there, home], projects.ONE_VILLAGE + 2, far + 30))
    w.tick += 1  # (the villages are looked up once a tick)
    assert len(projects.scopes(w)) == 2 and not projects.scopes(w)[0].whole
    return w, A, B, H


def _sc(w: World, a):
    w.__dict__.pop("_scopes", None)  # (a test moves chits and homes within a tick)
    return projects.scope_of(w, a)


def _keys(w: World, sc):
    return {(c[1], c[2]) for c in projects.candidates(w, sc)}


def _events(w: World, kind: str):
    return [e for e in w.events if e.kind == kind]


# ---------------------------------------------------------------------------------------------- what a village lacks
def test_a_daughter_village_gets_a_project_for_what_its_mother_already_has():
    w, A, B, _ = _two(far=projects.STATION_USE + 12)
    a, b = A[0], B[0]
    for c in (a, b):
        c.learn("recipe:cord", "discovered", w.tick)  # (a stockpile takes cord)
    for d in ("kiln", "workshop", "stockpile"):
        _put(w, a, d, (a.x, a.y - 4), 6)
        a.learn(f"design:{d}", "insight", w.tick)
        b.learn(f"design:{d}", "insight", w.tick)
        for m, k in DESIGNS[d].materials:  # (what each is built from, at hand)
            b.inventory[m] = b.inventory.get(m, 0) + k
    w.tick += 1
    mother, daughter = _sc(w, a), _sc(w, b)
    assert mother.id != daughter.id and max(abs(mother.x - daughter.x), abs(mother.y - daughter.y)) >= 40
    for s in w.structures.values():  # the mother's stations are farther off than a chit walks to one, its store than it sees
        if s.design in ("kiln", "workshop"):
            assert s.dist(daughter.x, daughter.y) > projects.STATION_USE
    # the mother has all three; the daughter, a day's walk off, has none it can use: each is a project it could take on
    assert not {("build", d) for d in ("kiln", "workshop", "stockpile")} & _keys(w, mother)
    assert {("build", d) for d in ("kiln", "workshop", "stockpile")} <= _keys(w, daughter)
    assert all(c[3] == "the village has none" for c in projects.candidates(w, daughter) if c[1] == "build" and c[2] == "kiln")
    # and it picks one by need, as its own project (the mother's is another matter)
    for c in projects.candidates(w, daughter):  # (the road to the next age set aside, to see the buildings picked)
        if c[1] != "build":
            w.civic["skips"].setdefault(daughter.id, {})[f"{c[1]}:{c[2]}"] = 10 ** 6
    p = projects.pick(w, sc=daughter)
    assert p["kind"] == "build" and p["key"] in ("kiln", "workshop", "stockpile") and p["chosen_by"] == "need"
    assert projects.of(w, daughter.id) is p and projects.of(w, mother.id) is None
    assert projects.current(w, b) is p and projects.current(w, a) is None
    ev = _events(w, "project")[-1]
    assert ev.text.startswith(f"{daughter.name} turned to a new project") and ev.data["village"] == daughter.id
    # once it has its own, it lacks it no more (and the mother's kiln never counted)
    _put(w, b, p["key"], (b.x, b.y + 6), 12)
    w.tick += 1
    assert ("build", p["key"]) not in _keys(w, _sc(w, b))


def test_a_station_near_enough_to_walk_to_is_not_lacking():
    # what a village can use is its own buildings and those within reach of its middle (a station as far as chits walk
    # to one, a store as far as they see one): a kiln just outside the houses is the village's kiln
    w, A, B, _ = _two()
    b = B[0]
    b.learn("design:kiln", "insight", w.tick)
    b.inventory.update(DESIGNS["kiln"].material_map)
    w.tick += 1
    daughter = _sc(w, b)
    assert ("build", "kiln") in _keys(w, daughter)
    kiln = _put(w, b, "kiln", (daughter.x + 14, daughter.y), 6)
    w.tick += 1
    daughter = _sc(w, b)
    assert kiln.id not in daughter.village.structures and kiln.dist(daughter.x, daughter.y) <= projects.STATION_USE
    assert ("build", "kiln") not in _keys(w, daughter)


def test_what_a_village_raised_beyond_its_houses_is_its_own():
    # a pen goes up by the sheep and a farm by the water, not among the houses: built once, it is not lacking again
    # (it was: the daughter raised a pen, still "had none", and raised another)
    w, A, B, _ = _two()
    b = B[0]
    b.learn("design:farm", "insight", w.tick)
    b.inventory.update(DESIGNS["farm"].material_map)
    w.tick += 1
    daughter, mother = _sc(w, b), _sc(w, A[0])
    assert ("build", "farm") in _keys(w, daughter)
    p = projects.start(w, "build", "farm", "the village has none", None, "need", sc=daughter)
    away = _spot(w, b, [(daughter.x, daughter.y)], projects.STORE_USE + 4, projects.JOIN_REACH - 6)
    assert max(abs(away[0] - mother.x), abs(away[1] - mother.y)) > max(abs(away[0] - daughter.x), abs(away[1] - daughter.y))
    w.tick = 10
    farm = w.place_site("farm", *w.find_site("farm", away[0], away[1], 2, reach=(b.x, b.y)), b)
    assert farm.dist(daughter.x, daughter.y) > projects.STORE_USE
    assert ("build", "farm") in _keys(w, _sc(w, b))  # (looked at this tick, with the farm still going up)
    farm.needs = {}
    w.complete_structure(farm, b)
    projects.tick(w)  # the same tick finishes the project and looks for the next
    assert [d["key"] for d in w.civic["done"]] == ["farm"] and p["id"] == w.civic["done"][0]["id"]
    assert (projects.of(w, daughter.id) or {}).get("key") != "farm"
    assert ("build", "farm") not in _keys(w, projects.scope_of(w, b))  # (in that same look at the villages)
    assert ("build", "farm") not in _keys(w, _sc(w, b))


def test_a_made_material_is_counted_in_the_stores_a_village_can_reach():
    w, A, B, _ = _two()
    a, b = A[0], B[0]
    pile = _put(w, a, "stockpile", (a.x, a.y - 5), 12)
    pile.storage["brick"] = 9
    b.inventory["brick"] = 2
    w.tick += 1
    mother, daughter = _sc(w, a), _sc(w, b)
    assert projects.stock(w, "brick") == 11  # (the whole world's, for the observer's road)
    assert projects.stock(w, "brick", sc=mother) == 9 and projects.stock(w, "brick", sc=daughter) == 2
    p = projects.start(w, "make", "brick", "test", None, "need", {"n": 4, "for": "kiln"}, sc=daughter)
    assert projects.status(w, p)[0] == "the village has 2 of 4"
    w.tick = 10
    projects.tick(w)
    assert projects.of(w, daughter.id) is p  # the mother's nine bricks, 50 tiles away, don't finish it


# ---------------------------------------------------------------------------------------------- two at once
def test_two_villages_hold_two_projects_and_each_completes_its_own():
    w, A, B, _ = _two()
    a, a2, b, b2 = A[0], A[1], B[0], B[1]
    for c in A + B:
        c.learn("design:kiln", "insight", w.tick)
        c.learn("design:well", "insight", w.tick)
    sa, sb = _sc(w, a), _sc(w, b)
    pa = projects.start(w, "build", "kiln", "the village has none", None, "need", sc=sa)
    pb = projects.start(w, "build", "well", "the village has none", None, "need", sc=sb)
    assert projects.of(w, sa.id) is pa and projects.of(w, sb.id) is pb and pa["id"] != pb["id"]
    assert sorted(w.civic["projects"]) == sorted([sa.id, sb.id])
    # each chit's scene carries its own village's project, never the other's
    assert "build a kiln" in projects.scene_line(w, a) and "well" not in projects.scene_line(w, a)
    assert "build a well" in projects.scene_line(w, b) and "kiln" not in projects.scene_line(w, b)
    assert "build a kiln" in "\n".join(P.village_lines(w, a)) and "build a well" in "\n".join(P.village_lines(w, b))
    assert projects.knows(w, a, pa) and not projects.knows(w, a, pb) and not projects.knows(w, b, pa)
    # a kiln going up by the mother is the mother's site, a well by the daughter the daughter's
    kiln = w.place_site("kiln", *w.find_site("kiln", a.x, a.y - 5, 8, reach=(a.x, a.y)), a)
    well = w.place_site("well", *w.find_site("well", b.x, b.y - 5, 8, reach=(b.x, b.y)), b)
    kiln.builders = {a.id: 4.0, a2.id: 1.0, b2.id: 2.0}  # (b2, of the other village, lent a hand at the kiln)
    well.builders = {b.id: 3.0}
    w.tick = 10
    projects.tick(w)
    assert pa["site"] == kiln.id and pb["site"] == well.id
    before = {c.id: c.renown for c in (a, a2, b, b2)}
    kiln.needs = {}
    w.complete_structure(kiln, a)
    w.tick = 20
    projects.tick(w)
    done = _events(w, "project_done")
    assert len(done) == 1 and done[0].data["village"] == sa.id and done[0].text.startswith(f"{sa.name}'s project done:")
    assert set(done[0].data["helpers"]) == {a.id, a2.id}  # the village's thanks go to its own chits
    # (everyone on the site of a world's first kiln earns 1 from the chronicle; the project's thanks come on top)
    assert a.renown > before[a.id] + 1 and a2.renown > before[a2.id] + 1 and b2.renown == before[b2.id] + 1
    assert not any("project is done" in m.text for m in b2.memories)
    assert projects.of(w, sb.id) is pb and (projects.of(w, sa.id) or {}).get("key") != "kiln"  # the well goes on
    well.needs = {}
    w.complete_structure(well, b)
    w.tick = 30
    projects.tick(w)
    done = _events(w, "project_done")
    assert len(done) == 2 and done[1].data["village"] == sb.id and done[1].data["helpers"] == [b.id]
    assert [(d["key"], d["village"]) for d in w.civic["done"]] == [("kiln", sa.id), ("well", sb.id)]


def test_a_building_finished_in_one_village_does_not_finish_the_others_project():
    w, A, B, _ = _two()
    a, b = A[0], B[0]
    sa, sb = _sc(w, a), _sc(w, b)
    pa = projects.start(w, "build", "kiln", "the village has none", None, "need", sc=sa)
    pb = projects.start(w, "build", "kiln", "the village has none", None, "need", sc=sb)
    w.tick = 5
    _put(w, b, "kiln", (b.x, b.y - 5), 8)
    w.tick = 10
    projects.tick(w)
    assert projects.of(w, sa.id) is pa and (projects.of(w, sb.id) or {}).get("id") != pb["id"]
    assert [d["village"] for d in w.civic["done"]] == [sb.id]


def test_the_want_to_help_raise_it_is_only_for_the_projects_own_village():
    w, A, B, _ = _two()
    a, b = A[0], B[0]
    for c in (a, b):
        c.learn("design:kiln", "insight", w.tick)
    projects.start(w, "build", "kiln", "the village has none", None, "need", sc=_sc(w, a))
    helps = lambda c: [o for _, o in wants.options(w, c) if o["kind"] == "build"]
    assert [o["text"] for o in helps(a)] == ["to help raise the village's kiln"] and helps(b) == []
    assert civic.project_options(Instinct(), w, b, random.Random(1)) == []


# ---------------------------------------------------------------------------------------------- hamlets and loners
def test_a_tiny_hamlet_works_on_the_nearest_villages_project():
    w, A, B, H = _two(n=14, hamlet=2)
    assert len(H) < projects.PROJECT_MIN_ADULTS
    a, b, h = A[0], B[0], H[0]
    sa, sb, sh = _sc(w, a), _sc(w, b), _sc(w, h)
    near = min((sa, sb), key=lambda s: (s.x - h.x) ** 2 + (s.y - h.y) ** 2)
    assert sh is not None and sh.id == near.id and len(projects.scopes(w)) == 2  # no slot of its own
    p = projects.start(w, "discover", "cord", "test", None, "need", sc=near)
    assert projects.current(w, h) is p and projects.knows(w, h, p) and "discover" in projects.scene_line(w, h)
    assert h in projects.members(w, near)
    rows = views.progress(w, [])["project"]["villages"]
    assert [r["with"] for r in rows] == ["", "", near.village.name] and rows[2]["active"] is None
    # a hamlet that grows to PROJECT_MIN_ADULTS carries its own
    hut = next(s for s in w.structures.values() if s.id == h.home)
    for c in B[-2:]:
        c.home, c.x, c.y = hut.id, h.x, h.y
    w.tick += 1
    assert len(projects.scopes(w)) == 3 and _sc(w, h).id not in (sa.id, sb.id)


def test_a_chit_with_no_home_belongs_to_the_nearest_village_within_reach_or_to_none():
    w, A, B, _ = _two()
    a, b, loner = A[0], B[0], A[-1]
    sa, sb = _sc(w, a), _sc(w, b)
    p = projects.start(w, "discover", "cord", "test", None, "need", sc=sb)
    loner.home = None
    loner.x, loner.y = sb.x + 5, sb.y
    assert _sc(w, loner).id == sb.id and projects.current(w, loner) is p
    loner.x, loner.y = sa.x + 3, sa.y
    assert _sc(w, loner).id == sa.id and projects.current(w, loner) is None
    # farther than JOIN_REACH from every village: no village, no project
    edge = max(((x, y) for x in (2, w.w - 3) for y in (2, w.h - 3)),
               key=lambda q: min(max(abs(q[0] - s.x), abs(q[1] - s.y)) for s in (sa, sb)))
    loner.x, loner.y = edge
    assert min(max(abs(edge[0] - s.x), abs(edge[1] - s.y)) for s in (sa, sb)) > projects.JOIN_REACH
    assert _sc(w, loner) is None and projects.current(w, loner) is None and projects.scene_line(w, loner) == ""
    assert civic.project_options(Instinct(), w, loner, random.Random(1)) == []


def test_a_chit_that_joins_a_village_is_counted_from_when_it_came():
    # its lifetime of experiments is not the village's work on a project begun before it arrived
    w, A, B, _ = _two()
    a, b = A[-1], B[0]
    a.bump("experiments", 7)
    sb = _sc(w, b)
    p = projects.start(w, "discover", "cord", "test", None, "need", sc=sb)
    a.home, a.x, a.y = b.home, b.x, b.y  # moves in with the daughter village
    w.tick = 10
    assert _sc(w, a).id == sb.id
    projects.tick(w)
    assert p["attempts"] == 0 and a.id not in p["helpers"]
    a.bump("experiments", 1)
    w.tick = 20
    projects.tick(w)
    assert p["attempts"] == 1 and a.id in p["helpers"]


def test_settlements_standing_side_by_side_are_one_village():
    # a village's houses in two clusters (the world finds two settlements) are not two project slots
    w = World("A", "A", 3, "direct", 128, 12)
    ags = list(w.agents.values())
    home = (ags[0].x, ags[0].y)
    near = _spot(w, ags[0], [home], 20, projects.ONE_VILLAGE - 4)
    _settle(w, ags[:6], home)
    _settle(w, ags[6:], near)
    w.tick += 1
    from chits.sim import pioneers

    assert len(pioneers.villages(w)) == 2
    [sc] = projects.scopes(w)
    assert sc.whole and all(_sc(w, c).id == sc.id for c in ags)


# ---------------------------------------------------------------------------------------------- old saves
def _old_save(w: World, project, skip):
    d = json.loads(json.dumps(w.to_dict()))
    civ = d["civic"]
    civ.pop("projects"), civ.pop("skips")
    civ["project"], civ["skip"] = project, skip
    civ["done"] = [{"id": "p1", "kind": "build", "key": "campfire", "day": 2, "started_day": 1, "text": "x", "helpers": 2,
                    "chosen_by": "need", "by_name": ""}]
    civ["seq"] = 2
    return d


def _old_project(key: str, site: str = ""):
    return {"id": "p2", "kind": "build", "key": key, "why": "the village has none", "by": "", "by_name": "",
            "chosen_by": "need", "tick": 0, "site": site, "seen": {}, "exp": {}, "attempts": 0, "helpers": {},
            "last_progress": 0}


def test_an_old_save_with_one_project_keeps_it_in_a_one_village_world():
    w = World("A", "A", 3, "direct", 64, 6)
    a = next(iter(w.agents.values()))
    a.learn("design:kiln", "insight", w.tick)
    w.leader = ""
    assert ("build", "kiln") in _keys(w, None)
    w2 = World.from_dict(_old_save(w, _old_project("well"), {"build:kiln": 10 ** 6}))
    assert "project" not in w2.civic and "skip" not in w2.civic
    assert projects.of(w2)["id"] == "p2" and projects.of(w2)["key"] == "well"
    assert [d["key"] for d in w2.civic["done"]] == ["campfire"]
    assert ("build", "kiln") not in _keys(w2, None)  # what it had set aside stays set aside
    w2.tick = 10
    projects.tick(w2)
    assert projects.of(w2)["id"] == "p2" and len(w2.civic["projects"]) == 1
    w3 = World.from_dict(json.loads(json.dumps(w2.to_dict())))  # and it saves in the new shape
    assert projects.of(w3)["id"] == "p2" and "project" not in w3.civic


def test_an_old_saves_project_goes_to_the_village_holding_its_site_else_the_largest():
    w, A, B, _ = _two(n=13)  # (the daughter is the larger: 6 and 7)
    a, b = A[0], B[0]
    sa, sb = _sc(w, a), _sc(w, b)
    assert sb.pop > sa.pop
    site = w.place_site("kiln", *w.find_site("kiln", a.x, a.y - 5, 8, reach=(a.x, a.y)), a)
    # with a site: the village the site stands in (the smaller one here)
    w2 = World.from_dict(_old_save(w, _old_project("kiln", site.id), {}))
    w2.tick += 10
    projects.tick(w2)
    assert projects.of(w2, sa.id)["id"] == "p2" and projects.of(w2, sb.id) is None
    assert [d["id"] for d in w2.civic["done"]] == ["p1"] and "" not in w2.civic["projects"]
    # with none: the largest village
    w3 = World.from_dict(_old_save(w, _old_project("well"), {"build:kiln": 10 ** 6}))
    w3.tick += 10
    projects.tick(w3)
    assert projects.of(w3, sb.id)["id"] == "p2" and projects.of(w3, sa.id) is None
    assert w3.civic["skips"] == {sb.id: {"build:kiln": 10 ** 6}}


# ---------------------------------------------------------------------------------------------- culture
def test_where_chits_cant_talk_a_village_project_is_known_only_by_sight_of_its_site():
    """The rules of a world without speech hold village by village: a project is not a thing that can be told, the
    world's own pick is never anyone's call, and a chit knows only the project of its own village."""
    w, A, B, _ = _two("stigmergy")
    assert not w.flags.get("say")
    a, a2, b, b2 = A[0], A[1], B[0], B[1]
    for c in A + B:
        c.learn("design:kiln", "insight", w.tick)
        c.inventory.update(DESIGNS["kiln"].material_map)
    w.leader = a.id  # (an elder: no chief is ever asked where chits can't talk)
    a.brain = "some-model"
    w.tick += 1
    sa, sb = _sc(w, a), _sc(w, b)
    projects.new_day(w)
    pa, pb = projects.of(w, sa.id), projects.of(w, sb.id)
    assert pa and pb and not w.civic.get("ask")
    for p, sc in ((pa, sa), (pb, sb)):  # the world's pick: by need, nobody's call, in neither village
        assert (p["chosen_by"], p["by"], p["by_name"]) == ("need", "", "")
    for ev in _events(w, "project"):
        assert "turned to a new project" in ev.text and "Chief" not in ev.text and "elder" not in ev.text
    # nobody was told: with no site in sight nobody knows either project, not even the elder
    for c in A + B:
        assert not projects.knows(w, c) and projects.scene_line(w, c) == "" and "Village project" not in P.scene(w, c)
        assert civic.project_options(Instinct(), w, c, random.Random(1)) == []
        assert not [o for _, o in wants.options(w, c) if o["kind"] == "build"]
    # a site goes up in the daughter village: those of that village who can see it know, and only they
    pb = projects.start(w, "build", "kiln", "the village has none", None, "need", sc=sb)
    site = w.place_site("kiln", *w.find_site("kiln", b.x, b.y - 4, 8, reach=(b.x, b.y)), b)
    w.tick += 10 - w.tick % 10
    projects.tick(w)
    assert pb["site"] == site.id
    b2.x, b2.y = min(w.w - 2, site.x + projects.SITE_SIGHT + 6), site.y  # of the village, but out of sight
    assert projects.knows(w, b, pb) and projects.scene_line(w, b).startswith("Village project: build a kiln (chosen by need)")
    assert not projects.knows(w, b2, pb) and projects.scene_line(w, b2) == ""
    # a chit of the other village standing by the site sees a building going up, not a project: it was never its own
    a2.x, a2.y = site.x + 1, site.y + 1
    assert _sc(w, a2).id == sa.id and not projects.knows(w, a2, pb) and "kiln" not in projects.scene_line(w, a2)
    assert not [o for _, o in wants.options(w, a2) if o["kind"] == "build"]
    assert civic.project_options(Instinct(), w, a2, random.Random(1)) == []
    # its thanks: an experiment by a chit that never knew of a discovery project is not help, in either village
    pd = projects.start(w, "discover", "cord", "test", None, "need", sc=sa)
    a.bump("experiments", 2)
    b.bump("experiments", 2)
    w.tick += 10
    projects.tick(w)
    assert pd["attempts"] == 2 and projects.helpers(w, pd) == []  # (the mother's tries only, and nobody was told)


def test_a_menu_or_scene_never_names_what_a_village_has_not_discovered():
    # a daughter that has not worked out cord hears the riddle, as its mother once did, though the mother knows cord
    w, A, B, _ = _two()
    a, b = A[0], B[0]
    w.first["design:campfire"] = {"tick": 1, "by": a.id, "name": a.name}  # Firekeepers: a stone axe (cord) is next
    for c in A:
        c.learn("recipe:cord", "discovered", w.tick)
    sa, sb = _sc(w, a), _sc(w, b)
    assert ("discover", "cord") not in _keys(w, sa) and ("discover", "cord") in _keys(w, sb)
    p = projects.start(w, "discover", "cord", "on the road", None, "need", sc=sb)
    line = projects.scene_line(w, b)
    assert line.startswith("Village project: discover something strong, binding and flexible")
    assert "cord" not in line and "fiber" not in line and projects.scene_line(w, a) == ""
    w.leader = b.id
    for words in projects.ideas(w):
        assert "cord" not in words and "fiber" not in words
    # and the mother's knowing it does not end the daughter's search
    w.tick = 10
    projects.tick(w)
    assert projects.of(w, sb.id) is p


# ---------------------------------------------------------------------------------------------- the chief
def test_the_chief_chooses_only_for_the_village_the_chief_lives_in():
    w, A, B, _ = _two()
    chief, b = A[0], B[0]
    for c in A + B:
        c.learn("design:kiln", "insight", w.tick)
        c.learn("design:farm", "insight", w.tick)
        c.inventory.update(DESIGNS["kiln"].material_map)
    w.leader, chief.brain = chief.id, "some-model"
    w.tick += 1
    sa, sb = _sc(w, chief), _sc(w, b)
    projects.new_day(w)
    ask = w.civic["ask"]
    # one question, for the chief's own village; the other village's need has already picked
    assert ask["leader"] == chief.id and ask["village"] == sa.id and projects.of(w, sa.id) is None
    pb = projects.of(w, sb.id)
    assert pb and (pb["chosen_by"], pb["by"]) == ("need", "") and "fallback" not in pb
    assert "chosen by need" in projects.scene_line(w, b) and "call" not in projects.scene_line(w, b).split("—")[0].replace("chosen by need", "")
    rng_before = w.rng_for("projects").getstate()
    projects.new_day(w)  # the question stands: nothing is asked or picked twice
    assert w.civic["ask"] is ask and w.rng_for("projects").getstate() == rng_before
    p = projects.answer(w, chief.id, 0)
    o = ask["options"][0]
    assert (p["kind"], p["key"], p["chosen_by"], p["by"]) == (o["kind"], o["key"], "chief", chief.id)
    assert projects.of(w, sa.id) is p and projects.of(w, sb.id) is pb and w.civic.get("ask") is None
    assert _events(w, "project")[-1].text.startswith(f"Chief {chief.name} called on {sa.name} to ")
    assert f"chief {chief.name}'s call" in projects.scene_line(w, A[1]) and "chief" not in projects.scene_line(w, b)
    # in its reflection too, a chief names a project for its own village only
    other = "farm" if p["key"] == "kiln" else "kiln"
    assert projects.name_project(w, chief, f"build a {other}")
    assert projects.of(w, sa.id)["key"] == other and projects.of(w, sb.id) is pb


def test_an_unanswered_chief_leaves_only_its_own_village_to_need():
    from chits.sim.agent import TICKS_PER_DAY

    w, A, B, _ = _two()
    chief, b = A[0], B[0]
    for c in A + B:
        c.learn("design:kiln", "insight", w.tick)
        c.inventory.update(DESIGNS["kiln"].material_map)
    w.leader, chief.brain = chief.id, "some-model"
    w.tick += 1
    sa, sb = _sc(w, chief), _sc(w, b)
    projects.new_day(w)
    pb = projects.of(w, sb.id)
    w.tick += projects.ASK_DAYS * TICKS_PER_DAY + 1
    pb["last_progress"] = w.tick
    projects._expire_ask(w)
    pa = projects.of(w, sa.id)
    assert pa["chosen_by"] == "need" and pa["fallback"] == "the chief's mind was never asked (unavailable)"
    assert projects.of(w, sb.id) is pb and "fallback" not in pb


# ---------------------------------------------------------------------------------------------- the observer
def test_the_observer_sees_each_villages_project():
    w, A, B, _ = _two()
    a, b = A[0], B[0]
    sa, sb = _sc(w, a), _sc(w, b)
    projects.start(w, "discover", "cord", "test", None, "need", sc=sb)
    w.leader = b.id
    v = views.progress(w, [])["project"]
    assert [r["id"] for r in v["villages"]] == [sb.id, sa.id]  # the chief's village first
    assert v["villages"][0]["name"] == sb.name and v["villages"][0]["active"]["title"] == "discover how to make cord"
    assert 0 <= v["villages"][0]["active"]["progress"] <= 1 and v["villages"][1]["active"] is None
    assert v["active"] == v["villages"][0]["active"]
    # a one-village world: one row, the same project as before
    w1 = World("A", "A", 3, "direct", 64, 6)
    p = projects.start(w1, "discover", "cord", "test", None, "need")
    v1 = views.progress(w1, [])["project"]
    assert len(v1["villages"]) == 1 and v1["active"]["id"] == p["id"] == v1["villages"][0]["active"]["id"]


def test_a_project_follows_its_village_when_the_villages_id_changes():
    # a settlement is named for its oldest building: when that falls, the village goes on under another id
    w, A, B, _ = _two()
    b = B[0]
    sb = _sc(w, b)
    p = projects.start(w, "discover", "cord", "test", None, "need", sc=sb)
    old = sb.id
    first = w.structures[old]
    _put(w, b, "hut", (first.x, first.y + 5), 5)  # (the village still stands without it)
    first.durability = 0
    w.tick += 10 - w.tick % 10
    projects.tick(w)
    now = _sc(w, b)
    assert now.id != old and projects.of(w, now.id) is p and old not in w.civic["projects"]
    assert not [e for e in _events(w, "project") if e.data.get("abandoned")]
