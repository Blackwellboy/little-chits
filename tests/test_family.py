"""Family trees and how knowledge spread (views.family, views.spread), living and dead."""

from chits import views
from chits.sim.world import World


def _world():
    w = World("A", "A", 5, "direct", 64, 4)
    return w, list(w.agents.values())


def test_a_family_reaches_grandparents_and_grandchildren_and_keeps_the_dead():
    w, (a, b, c, d) = _world()
    home = w.place_site("hut", *w.find_site("hut", a.x, a.y, 8), a)
    w.complete_structure(home, a)
    kid = w._make_child(a, b, home)
    kid2 = w._make_child(a, b, home)
    grandkid = w._make_child(kid, c, home)
    w.kill(a, "old age")
    f = views.family(w, kid.id)
    assert {p["name"] for p in f["parents"]} == {a.name, b.name}
    assert [s["name"] for s in f["siblings"]] == [kid2.name] and [g["name"] for g in f["children"]] == [grandkid.name]
    dead = next(p for p in f["parents"] if p["id"] == a.id)
    assert dead["alive"] is False and dead["cause"] == "old age"
    g = views.family(w, grandkid.id)
    assert {x["name"] for x in g["grandparents"]} == {a.name, b.name}
    assert views.family(w, a.id)["grandchildren"][0]["name"] == grandkid.name
    assert views.family(w, "nobody") is None


def test_the_spread_of_a_thing_runs_from_whoever_found_it():
    w, (a, b, c, d) = _world()
    a.learn("recipe:cord", "discovered", w.tick)
    w.tick = 240
    w.learned(b, "recipe:cord", "taught", a)
    w.tick = 480
    w.learned(c, "recipe:cord", "observed", b)
    w.kill(a, "old age")  # the finder is dead: it stays at the root
    t = views.spread(w, "recipe:cord")
    assert t["knowers"] == 3 and t["alive"] == 2 and t["name"] == "cord"
    (root,) = t["roots"]
    assert (root["name"], root["how"], root["alive"]) == (a.name, "discovered", False)
    (child,) = root["passed_to"]
    assert (child["name"], child["how"], child["day"]) == (b.name, "taught", 2)
    assert child["passed_to"][0]["name"] == c.name and child["passed_to"][0]["how"] == "observed"


def test_the_eras_endpoint_names_each_ages_first_maker():
    w, (a, b, c, d) = _world()
    w.first["design:campfire"] = {"tick": 30, "by": a.id, "name": a.name}
    w.built_designs["campfire"] = w.first["design:campfire"]  # (deeds: the age needs one standing, not just known)
    w.first["recipe:stone_axe"] = {"tick": 500, "by": b.id, "name": b.name}
    w.update_era()
    e = views.eras(w)
    assert e["index"] == 2 and e["name"] == "Toolmakers"
    assert e["heroes"] == [{"era": "Firekeepers", "who": a.name, "day": 1}, {"era": "Toolmakers", "who": b.name, "day": 3}]


def test_the_spread_tree_keeps_visitors_and_loops_of_teachers():
    w, (a, b, c, d) = _world()
    w.tick = 240
    w.learned(a, "recipe:cord", "taught", b)
    w.learned(b, "recipe:cord", "taught", a)  # a record loop with no finder at its head
    c.learn("recipe:cord", "discovered", w.tick)
    d.origin = "B"
    w.learned(d, "recipe:cord", "taught", c)  # its teacher's id is from over the sea: here it names someone else
    t = views.spread(w, "recipe:cord")
    names = set()

    def walk(n):
        names.add(n["name"])
        for k in n["passed_to"]:
            walk(k)

    for r in t["roots"]:
        walk(r)
    assert t["knowers"] == 4 and names == {a.name, b.name, c.name, d.name}
    assert d.name in {r["name"] for r in t["roots"]}
