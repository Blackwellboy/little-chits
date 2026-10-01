"""Food security (sim/food.py): with the stores running low, the village's project waits and chits fill them."""

import random

from chits import views
from chits.brain import civic
from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim import food, projects
from chits.sim.world import World


class Low(random.Random):
    """An rng that always rolls low: whatever happens 'sometimes' happens now."""

    def random(self):
        return 0.01


def _village(stored: dict, culture="direct"):
    w = World("A", "A", 3, culture, 64, 4)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():  # everyone at home, fed
        o.x, o.y = a.x, a.y
        o.hunger = o.energy = o.warmth = 95.0
    pos = w.find_site("stockpile", a.x + 2, a.y, 8)
    pile = w.place_site("stockpile", pos[0], pos[1], a)
    w.complete_structure(pile, a)
    pile.storage.update(stored)
    w.tick = 240 * 1  # spring (in summer and autumn the winter stockpiling comes first)
    return w, a, pile


def test_days_of_food_are_counted_from_the_stores_a_chit_can_see():
    w, a, pile = _village({"bread": 20})  # 20 x 55 = 1100 hunger for 4 chits at 45 a day
    assert food.food_days(w, a) == round(1100 / (4 * food.FOOD_PER_DAY), 1)
    assert food.food_days(w) == food.food_days(w, a)
    far = list(w.agents.values())[1]
    far.x, far.y = min(w.w - 2, a.x + 40), a.y
    assert food.food_days(w, far) is None  # it can't see those stores
    assert views.progress(w, [])["food_days"] == food.food_days(w)


def test_with_the_stores_low_the_project_waits_and_chits_fill_them():
    w, a, pile = _village({"berries": 4})
    a.familiar |= {"fiber", "wood", "stone"}
    p = projects.start(w, "discover", "cord", "test", None, "need")
    assert food.short(w, a)
    ins = Instinct()
    ins._world = w
    assert civic.duty(ins, w, a, Low(1)) is None
    plan = ins._communal(w, a, Low(1))
    assert plan["goal"] == "fill the stores" and plan["steps"][-1]["do"] == "store"
    assert "food first" in projects.scene_line(w, a) and "too little" in P.scene(w, a)
    # with the stores full, the project comes first again
    pile.storage["bread"] = 40
    assert not food.short(w, a)
    assert civic.duty(ins, w, a, Low(1)) is not None
    assert "food first" not in projects.scene_line(w, a)
    assert all(s.get("_proj") == p["id"] for s in ins._communal(w, a, Low(1))["steps"])


def test_the_project_weighs_less_among_a_hungry_chits_options():
    w, a, pile = _village({"berries": 2})
    a.familiar |= {"fiber", "wood", "stone"}
    projects.start(w, "discover", "cord", "test", None, "need")
    ins = Instinct()
    base = civic.project_options(ins, w, a, random.Random(3))
    extended = civic.extend(ins, w, a, random.Random(3), [])
    tagged = [wt for wt, o in extended if any(s.get("_proj") for s in o["steps"])]
    assert base and tagged and max(tagged) <= max(wt for wt, _ in base) * civic.FOOD_FIRST + 1e-9


def test_a_village_without_stores_has_none_to_run_low():
    w = World("A", "A", 3, "direct", 64, 4)
    a = next(iter(w.agents.values()))
    assert food.food_days(w, a) is None and not food.short(w, a) and food.scene_line(w, a) is None
    assert views.progress(w, [])["food_days"] is None


def test_an_outpost_camps_store_is_not_the_village_stores():
    w, a, pile = _village({"berries": 4})
    camp = w.place_site("outpost", *w.find_site("outpost", a.x, a.y + 2, 8), a)
    w.complete_structure(camp, a)
    before = food.food_days(w, a)
    camp.storage["bread"] = 100  # food in a far camp feeds nobody at home (and rots there without a granary)
    assert food.food_days(w, a) == before and food.short(w, a)
    ins = Instinct()
    ins._world = w
    plan = ins._communal(w, a, Low(1))
    assert plan["goal"] == "fill the stores" and plan["steps"][-1]["target"] == pile.id
