import json

from chits.brain import prompt as P
from chits.sim.world import World


def world_with_fire():
    w = World("A", "A", 21, "direct", 96, 4)
    a = next(iter(w.agents.values()))
    pos = w.find_site("campfire", a.x, a.y)
    s = w.place_site("campfire", pos[0], pos[1], a)
    w.complete_structure(s, a)
    pos = w.find_site("hut", a.x + 4, a.y + 4)
    h = w.place_site("hut", pos[0], pos[1], a)
    w.complete_structure(h, a)
    return w, s, h


def test_default_and_clock():
    w = World("A", "A", 1, "direct", 96, 4)
    assert w.weather == "clear" and w.clock()["weather"] == "clear"


def test_storm_puts_out_fires_and_damages():
    w, fire, hut = world_with_fire()
    evs = []
    w.listeners.append(evs.append)
    t0 = w.temperature()
    assert fire.lit
    w.set_weather("storm")
    assert not fire.lit and fire.fuel == 0
    assert w.clock()["weather"] == "storm"
    assert any(e.kind == "storm" and e.importance == 4 for e in evs)
    assert abs((t0 - w.temperature()) - 0.15) < 1e-6
    assert "storm" in P.scene(w, next(iter(w.agents.values()))).split("\n")[0].lower()
    n = len(evs)
    w.set_weather("storm")  # no-op
    assert len(evs) == n


def test_storm_damage_is_probabilistic_but_real():
    hits = 0
    for seed in range(20):
        w, fire, hut = world_with_fire()
        w.rng.seed(seed)
        w.set_weather("storm")
        hits += hut.durability < 100
    assert 2 <= hits <= 14


def test_drought_stops_regrowth():
    w = World("A", "A", 5, "direct", 96, 0)
    idx = [i for i, k in enumerate(w.res_kind) if k == 4][:200]  # berry bushes
    for i in idx:
        w.res_amt[i] = 0
    w.set_weather("drought", days=5)
    for _ in range(600):
        w.step()
    assert sum(w.res_amt[i] for i in idx) == 0
    w.set_weather("rain", days=5)
    for _ in range(600):
        w.step()
    assert sum(w.res_amt[i] for i in idx) > 0


def test_daily_roll_and_persistence():
    seen = set()
    for seed in (9, 10, 11):
        w = World("A", "A", seed, "direct", 64, 0)
        for _ in range(240 * 24):
            w.step()
            seen.add(w.weather)
    assert "snow" in seen and "rain" in seen and ("storm" in seen or "drought" in seen)
    w.set_weather("rain", days=2)
    w2 = World.from_dict(json.loads(json.dumps(w.to_dict())))
    assert w2.weather == "rain" and w2.weather_until == w.weather_until
    d = w.to_dict()
    d.pop("weather", None)
    d.pop("weather_until", None)
    assert World.from_dict(json.loads(json.dumps(d))).weather == "clear"


# ---- common sense: get out of the weather ----------------------------------------------------------------
def _outside_spot(w, hut, fire, dmin=6, dmax=14):
    for r in range(dmin, dmax + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                x, y = hut.x + dx, hut.y + dy
                if not (0 <= x < w.w and 0 <= y < w.h) or not w.passable(x, y):
                    continue
                if w.occupied.get(y * w.w + x) or max(abs(x - fire.x), abs(y - fire.y)) <= 4:
                    continue
                return x, y
    raise AssertionError("no outside spot")


def _ready(a):
    a.plan = []
    a.hunger = a.energy = a.warmth = a.health = 100.0


def test_storm_sends_chits_inside():
    w, fire, hut = world_with_fire()
    a = next(iter(w.agents.values()))
    a.x, a.y = _outside_spot(w, hut, fire)
    _ready(a)
    w.set_weather("storm", days=2)
    assert not w.sheltered(a) and w.exposure(a) > 0
    for _ in range(220):
        w.step()
        if w.sheltered(a):
            break
    assert w.sheltered(a), "a chit caught in a storm should get indoors"
    assert w.exposure(a) == 0


def test_exposure_and_shelter_rules():
    w, fire, hut = world_with_fire()
    a, b = list(w.agents.values())[:2]
    cx, cy = hut.x, hut.y
    a.x, a.y = cx, cy
    b.x, b.y = _outside_spot(w, hut, fire)
    for kind, lo in (("storm", 0.3), ("snow", 0.15), ("rain", 0.01)):
        w.set_weather(kind, days=2)
        assert w.sheltered(a) and w.exposure(a) == 0
        assert not w.sheltered(b) and w.exposure(b) >= lo
    w.set_weather("clear", days=1)
    assert w.exposure(b) == 0
    # a lit fire shelters from snow, but not from a storm (the storm puts it out anyway)
    w.set_weather("snow", days=2)
    fx, fy = fire.x, fire.y
    spot = next((fx + dx, fy + dy) for dx in (-2, -1, 1, 2) for dy in (-2, -1, 0, 1, 2)
                if 0 <= fx + dx < w.w and 0 <= fy + dy < w.h and w.passable(fx + dx, fy + dy))
    if not fire.lit:
        fire.fuel = 50
    assert fire.lit
    b.x, b.y = spot
    assert w.sheltered(b)


def test_exposed_chits_lose_warmth_faster():
    w, fire, hut = world_with_fire()
    a, b = list(w.agents.values())[:2]
    cx, cy = hut.x, hut.y
    w.set_weather("storm", days=2)
    for c in (a, b):
        _ready(c)
        c.warmth = 50.0
        c.plan = [{"do": "rest"}] * 3
    a.x, a.y = cx, cy
    b.x, b.y = _outside_spot(w, hut, fire)
    b.plan = [{"do": "rest", "_reflex": True}]  # a reflex head stops the shelter reflex for this one tick
    w.step()
    assert b.warmth < a.warmth - 0.3


def test_shelter_verb_and_prompt():
    from chits.sim import actions as A

    assert "shelter" in A.VERBS
    for alias in ("take_cover", "go_inside", "hide"):
        assert A.normalize_verb(alias) == "shelter"
    w, fire, hut = world_with_fire()
    a, b = list(w.agents.values())[:2]
    assert "shelter" in P.verb_guide(w)
    w.set_weather("snow", days=2)
    b.x, b.y = _outside_spot(w, hut, fire)
    assert "out in it" in P.scene(w, b).split("\n")[0].lower()
    cx, cy = hut.x, hut.y
    a.x, a.y = cx, cy
    assert "under cover" in P.scene(w, a).split("\n")[0].lower()


def test_nowhere_to_shelter():
    w = World("A", "A", 4, "direct", 64, 1)
    a = next(iter(w.agents.values()))
    _ready(a)
    w.set_weather("storm", days=2)
    a.plan = [{"do": "shelter"}]
    for _ in range(5):
        w.step()
        if not a.plan or a.plan[0].get("do") != "shelter":
            break
    assert "nowhere" in a.last_result.lower()
