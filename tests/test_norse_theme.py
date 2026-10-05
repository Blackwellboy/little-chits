"""The opt-in Norse theme (`CHITS_THEME=norse`) renames new chits and worlds, and changes nothing else.

The names are drawn by the same syllable generator and shown through a fixed table, so the simulation's random
streams, and so everything the chits do, are the same with the theme on or off.
"""

import asyncio
import json
import os
import random
import re

import pytest

from chits import theme
from chits.brain.instinct import Instinct
from chits.runtime import Runtime
from chits.sim.agent import _SYL_A, _SYL_B, make_name
from chits.sim.world import Structure, World

# The syllable generator as it was before themes: an independent copy to compare against, not a call into the
# code under test. Don't change it to suit the theme.
_UP_A = "pi mo ta bi ru ke lo za fi nu do ve sa yo mi ga pe wu ri ko".split()
_UP_B = "p x n b ra lo mi sh tt ck ndo va zz ri ble po ki m l ssa".split()


def upstream_name(rng, taken):
    for _ in range(200):
        n = rng.choice(_UP_A) + rng.choice(_UP_B)
        if rng.random() < 0.25:
            n += rng.choice(["o", "a", "i", "y"])
        n = n.capitalize()
        if n not in taken and 3 <= len(n) <= 7:
            return n
    rng = random.Random(f"names:{len(taken)}")  # (the longer names have a stream of their own, #57)
    for _ in range(400):
        n = (rng.choice(_UP_A) + rng.choice(_UP_A) + rng.choice(_UP_B)).capitalize()
        if n not in taken and len(n) <= 9:
            return n
    base = (rng.choice(_UP_A) + rng.choice(_UP_B)).capitalize()
    k = 2
    while f"{base}{k}" in taken:
        k += 1
    return f"{base}{k}"


@pytest.fixture(autouse=True)
def no_theme(monkeypatch):
    monkeypatch.delenv("CHITS_THEME", raising=False)


def norse():
    return theme.norse_names(tuple(_SYL_A), tuple(_SYL_B))


@pytest.mark.parametrize("value", [None, "", "default", "viking", "nors"])
def test_without_the_theme_names_are_exactly_the_syllable_names(monkeypatch, value):
    if value is not None:
        monkeypatch.setenv("CHITS_THEME", value)
    assert theme.active() == "default"
    ref, rng, taken = random.Random(15), random.Random(15), set()
    for _ in range(400):
        want = upstream_name(ref, taken)
        assert make_name(rng, taken) == want
        assert rng.getstate() == ref.getstate()
        taken.add(want)


@pytest.mark.parametrize("value", ["norse", "Norse", " NORSE "])
def test_the_theme_is_switched_on_by_name(monkeypatch, value):
    monkeypatch.setenv("CHITS_THEME", value)
    assert theme.active() == "norse"
    assert make_name(random.Random(1), set()) in norse().reverse


def test_norse_names_draw_exactly_what_the_syllable_names_draw(monkeypatch):
    """Through all three kinds of syllable name: short, then longer once those run out, then numbered."""
    monkeypatch.setenv("CHITS_THEME", "norse")
    names = norse()
    ref, rng = random.Random(1234), random.Random(1234)
    plain, themed = set(), set()
    for i in range(10_400):
        want = upstream_name(ref, plain)
        got = make_name(rng, themed)
        assert rng.getstate() == ref.getstate(), i
        assert got not in themed and names.to_syllables(got) == want, (got, want)
        assert not re.search(r"\d", got)
        plain.add(want)
        themed.add(got)
    assert len(themed) == 10_400
    assert any(n.endswith(" II") for n in themed)  # reached the numbered names
    assert sum(1 for n in themed if n.split()[0] in theme.GIVEN) >= 1940


def test_the_name_table_is_one_to_one_and_reversible():
    names = norse()
    assert len(names.forward) == len(names.reverse) == 1940 + 8000
    for syl, nor in names.forward.items():
        assert names.to_norse(syl) == nor and names.to_syllables(nor) == syl
    assert names.to_syllables(names.to_norse("Pip17")) == "Pip17"
    assert names.to_norse("Pip17").endswith(" XVII")
    # any other name, from an old save or typed in, stands for itself
    for other in ("Pilo", "Chit42", "Astrid the Bold", "Astrid of the Fjord I", "Astrid of the Fjord IIII"):
        if other not in names.reverse:
            assert names.to_syllables(other) == other


def test_old_syllable_names_still_cost_the_same_draws(monkeypatch):
    """A save started without the theme, then run with it: the old names still block what they blocked."""
    old = set()
    ref = random.Random(3)
    for _ in range(300):
        old.add(upstream_name(ref, old))
    monkeypatch.setenv("CHITS_THEME", "norse")
    ref, rng = random.Random(77), random.Random(77)
    plain, themed = set(old), set(old)
    for _ in range(300):
        want = upstream_name(ref, plain)
        got = make_name(rng, themed)
        assert rng.getstate() == ref.getstate() and norse().to_syllables(got) == want
        plain.add(want)
        themed.add(got)


def test_names_do_not_depend_on_the_process_hash_seed():
    import subprocess
    import sys
    from pathlib import Path
    code = ("import json, random; from chits.sim.agent import make_name\n"
            "r, t = random.Random(9), set()\n"
            "for _ in range(50): t.add(make_name(r, t))\n"
            "print(json.dumps(sorted(t)))")
    server = str(Path(__file__).resolve().parents[1] / "server")
    out = [subprocess.check_output([sys.executable, "-c", code], text=True,
                                   env={**os.environ, "CHITS_THEME": "norse", "PYTHONHASHSEED": seed,
                                        "PYTHONPATH": server})
           for seed in ("1", "4242")]
    assert out[0] == out[1] and "of the" in out[0]


# ------------------------------------------------------------------ worlds


def _world(monkeypatch, on, seed=21, size=96, n=14):
    if on:
        monkeypatch.setenv("CHITS_THEME", "norse")
    else:
        monkeypatch.delenv("CHITS_THEME", raising=False)
    return World("A", "World A", seed, "direct", size, n)


def _run(monkeypatch, w, on, ticks):
    """Step a world on instinct, with the theme as it was when the world was made (births name chits)."""
    if on:
        monkeypatch.setenv("CHITS_THEME", "norse")
    else:
        monkeypatch.delenv("CHITS_THEME", raising=False)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    for _ in range(ticks):
        w.step(hook)


def _family(w):
    """Births through ten generations, and a death, so names must stay unique among the living and the dead."""
    parents = list(w.agents.values())[:2]
    home = Structure("s-fixture", "hut", *w.spawn, 3, 3, parents[0].id, 0, complete=True)
    w.structures[home.id] = home
    for _ in range(10):
        kids = [w._make_child(*parents, home) for _ in range(4)]
        parents = kids[:2]
    w.kill(list(w.agents.values())[2], "old age")


def _unthemed(plain: World, themed: World) -> dict:
    """The themed world's state with every chit's Norse name put back to its syllable name (matched by id)."""
    people = {**themed.agents, **themed.dead}
    others = {**plain.agents, **plain.dead}
    assert set(people) == set(others)
    swap = {people[i].name: others[i].name for i in people}
    assert all(k in norse().reverse for k in swap)
    swap.update({k.lower(): v.lower() for k, v in list(swap.items())})  # (an action keeps the name it was asked for, lowercased)
    pat = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(k) for k in sorted(swap, key=len, reverse=True))
                     + r")(?![A-Za-z])")
    return json.loads(pat.sub(lambda m: swap[m.group(1)], json.dumps(_comparable(themed))))


def _comparable(w: World) -> dict:
    d = w.to_dict()
    for k in ("uuid", "epoch", "epochs"):  # a fresh random id per world, theme or not
        d.pop(k)
    d["agents"] = [{**a, "plan": [{k: v for k, v in s.items() if k != "_step_id"} for s in a["plan"]]}
                   for a in d["agents"]]  # and per plan step (uuid4)
    return json.loads(json.dumps(d, default=str))


def test_same_seed_same_world_with_the_theme_on_or_off(monkeypatch):
    """Two in-game days on instinct, then births and a death: identical apart from the names chits are shown by."""
    plain, themed = _world(monkeypatch, False), _world(monkeypatch, True)
    _run(monkeypatch, plain, False, 2 * 240)
    _run(monkeypatch, themed, True, 2 * 240)
    for w, on in ((plain, False), (themed, True)):
        if on:
            monkeypatch.setenv("CHITS_THEME", "norse")
        else:
            monkeypatch.delenv("CHITS_THEME", raising=False)
        _family(w)

    assert all(a.name in norse().reverse for a in list(themed.agents.values()) + list(themed.dead.values()))
    assert not any(a.name in norse().reverse for a in list(plain.agents.values()) + list(plain.dead.values()))
    # the parts that matter, compared directly
    assert {k: r.getstate() for k, r in plain._rngs.items()} == {k: r.getstate() for k, r in themed._rngs.items()}
    assert plain._tick_streams_dict() == themed._tick_streams_dict()  # (this tick's streams, world.RNG_STREAMS on)
    assert plain.tick == themed.tick and plain.counters == themed.counters
    assert plain.tiles == themed.tiles and list(plain.res_amt) == list(themed.res_amt)
    for aid, a in {**plain.agents, **plain.dead}.items():
        b = {**themed.agents, **themed.dead}[aid]
        assert (a.x, a.y, a.inventory, a.knows, a.hunger, a.health, a.home, a.generation, a.parents) == \
               (b.x, b.y, b.inventory, b.knows, b.hunger, b.health, b.home, b.generation, b.parents), aid
    assert [s.to_dict() for s in plain.structures.values()] == [s.to_dict() for s in themed.structures.values()]
    assert [(e.tick, e.kind, e.actor) for e in plain.events] == [(e.tick, e.kind, e.actor) for e in themed.events]
    # and everything else in the save
    assert _unthemed(plain, themed) == _comparable(plain)


# ------------------------------------------------------------------ runtime and API


@pytest.fixture
def env(monkeypatch, tmp_path):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "8")
    monkeypatch.setenv("CHITS_MODE", "versus")
    return tmp_path


@pytest.mark.parametrize("on", [False, True])
def test_world_names_and_hello(env, monkeypatch, on):
    if on:
        monkeypatch.setenv("CHITS_THEME", "norse")
    rt = Runtime(env)
    try:
        want = ["Fjordhaven", "Pineholm"] if on else ["World A", "World B"]
        assert [w.name for w in rt.worlds.values()] == want
        assert [w.id for w in rt.worlds.values()] == ["A", "B"]
        hello = rt.hello()
        assert [m["name"] for m in hello["worlds"]] == want
        assert hello["theme"] == ("norse" if on else "default")
        # twin worlds stay twins
        assert [a.to_dict() for a in rt.worlds["A"].agents.values()] == [a.to_dict() for a in rt.worlds["B"].agents.values()]
    finally:
        asyncio.run(rt.mind.close())
        rt.store.db.close()


def test_a_saved_world_keeps_its_names_when_the_theme_changes(env, monkeypatch):
    rt = Runtime(env)
    try:
        before = {w.id: (w.name, sorted(a.name for a in w.agents.values())) for w in rt.worlds.values()}
        rt.save_all()
    finally:
        asyncio.run(rt.mind.close())
        rt.store.db.close()
    monkeypatch.setenv("CHITS_THEME", "norse")
    back = Runtime(env)
    try:
        assert {w.id: (w.name, sorted(a.name for a in w.agents.values())) for w in back.worlds.values()} == before
    finally:
        asyncio.run(back.mind.close())
        back.store.db.close()


@pytest.mark.parametrize("on", [False, True])
def test_health_reports_the_theme(env, monkeypatch, on):
    from fastapi.testclient import TestClient
    if on:
        monkeypatch.setenv("CHITS_THEME", "norse")
    from chits.app import app
    with TestClient(app) as c:
        assert c.get("/api/health").json()["theme"] == ("norse" if on else "default")
        assert c.get("/api/replay/export?days=1").json()["theme"] == ("norse" if on else "default")
        names = [w["name"] for w in c.get("/api/worlds").json()]
        assert names == (["Fjordhaven", "Pineholm"] if on else ["World A", "World B"])
