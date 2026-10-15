"""The modern town (world.CITY_GROWTH, issue #168): a tower block that only a city builds and that houses 24, and a
hospital whose sick heal four times as fast and whose neighbours live ten days longer."""

import pytest

from chits.sim import actions
from chits.sim import buildings as BLD
from chits.sim import world as W
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.items import DESIGNS
from test_buildings import put, village


def test_a_tower_block_is_a_city_home_for_24_rebuilt_from_an_apartment_block():
    assert BLD.HOME_CAP["tower_block"] == 24 and "tower_block" in BLD.WARM_HOMES
    assert "tower_block" in BLD.UPGRADES["apartment"] and "tower_block" in BLD.CITY_ONLY
    w, (a, _) = village()
    a.learn("design:tower_block", "taught", w.tick)
    a.inventory.update({k: n for k, n in DESIGNS["tower_block"].materials})
    msg = actions.advance(w, a, {"do": "build", "what": "tower_block"})
    assert "only a city" in msg  # a village can't raise one


def _old_neighbour(w, a, hospital: bool):
    home = put(w, "brick_house", a)
    a.home = home.id
    if hospital:
        put(w, "hospital", a, near=(home.x + 4, home.y), radius=10)
    w.__dict__.pop("_bfx", None)
    a.hunger = a.energy = a.warmth = a.health = 95.0
    a.born = w.tick - a.lifespan - 1  # just past its span
    return a


@pytest.mark.parametrize("hospital", [True, False])
def test_a_hospital_near_home_gives_ten_more_days(hospital, monkeypatch):
    w, (a, _) = village()
    _old_neighbour(w, a, hospital)
    assert BLD.life_bonus(w, a) == (BLD.HOSPITAL_DAYS * TICKS_PER_DAY if hospital else 0)
    w.step()
    assert (a.id in w.agents) is hospital  # without one, old age takes it now
    if hospital:
        a.born = w.tick - a.lifespan - BLD.HOSPITAL_DAYS * TICKS_PER_DAY - 1
        w.step()
        assert a.id not in w.agents  # ten days, not for ever


def test_without_city_growth_the_hospital_adds_no_days(monkeypatch):
    monkeypatch.setattr(W, "CITY_GROWTH", False)
    w, (a, _) = village()
    _old_neighbour(w, a, True)
    w.step()
    assert a.id not in w.agents


def test_the_sick_heal_four_times_as_fast_by_a_hospital():
    w, (a, _) = village()
    assert BLD.heal_mult(w, a) == 1.0
    put(w, "hospital", a)
    w.__dict__.pop("_bfx", None)
    assert BLD.heal_mult(w, a) == BLD.HOSPITAL_MULT == 4.0


def test_outside_a_city_an_apartment_is_not_rebuilt_as_a_tower_block():
    """The rebuild-in-place path went round the city check: a tower block went up in a hamlet."""
    w, (a, _) = village()
    flat = put(w, "apartment", a)
    a.home = flat.id
    a.learn("design:tower_block", "taught", w.tick)
    a.inventory.update({k: n for k, n in DESIGNS["tower_block"].materials})
    assert BLD.upgrade_instead(w, a, "tower_block", {"do": "build", "what": "tower_block"}) is None
    msg = actions.advance(w, a, {"do": "build", "what": "tower_block"})
    assert "only a city" in msg and not flat.upgrade
    assert "only a city" in actions.advance(w, a, {"do": "upgrade", "target": flat.id, "to": "tower_block"})


def test_switched_off_the_modern_town_is_neither_built_nor_felt(monkeypatch):
    from chits.sim import projects
    monkeypatch.setattr(W, "CITY_GROWTH", False)
    w, (a, _) = village()
    a.learn("design:hospital", "taught", w.tick)
    a.inventory.update({k: n for k, n in DESIGNS["hospital"].materials})
    assert "nobody here builds" in actions.advance(w, a, {"do": "build", "what": "hospital"})
    real = projects.next_step
    monkeypatch.setattr(projects, "next_step", lambda world, d, r, h, kind, key, *args, **kw: ("build", key, {})
                        if key == "hospital" else real(world, d, r, h, kind, key, *args, **kw))  # (it could be built)
    assert not any(c[2] == "hospital" for c in projects.candidates(w))
    monkeypatch.setattr(W, "CITY_GROWTH", True)
    assert any(c[2] == "hospital" for c in projects.candidates(w))  # (the gate, not the village, keeps it out)
    monkeypatch.setattr(W, "CITY_GROWTH", False)
    put(w, "hospital", a)  # (one standing anyway, from a save made with the switch on)
    w.__dict__.pop("_bfx", None)
    assert BLD.heal_mult(w, a) == 1.0  # (as on main: no hospital effect)
