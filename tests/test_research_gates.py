"""Acceptance gates from docs/RESEARCH_PLAN_2026-09-30.md, checked where the code already makes a promise.

Gates the code meets are plain tests. Gates the current belief system (T21) breaks are strict xfails: each says what
the strict worldview contract (plan item 50, R8) must change, and turns into a failure (XPASS) the day it is fixed, so
the marker has to come off. See docs/RESEARCH_READINESS.md for the whole table.
"""

import ast
import copy
import json
from pathlib import Path

import pytest

from chits.brain.instinct import Instinct
from chits.lab import run
from chits.lab import treatment as T
from chits.lab.spec import ExperimentSpec
from chits.sim import actions, lore
from chits.sim.agent import TICKS_PER_DAY
from chits.sim.world import Tablet, World

CHITS = Path(__file__).resolve().parent.parent / "server" / "chits"


def _imports(pkg: str):
    """(file, imported module) for every import in chits/<pkg>, relative ones resolved to chits.*."""
    out = []
    for f in sorted((CHITS / pkg).rglob("*.py")):
        here = ["chits", *f.relative_to(CHITS).parent.parts]
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Import):
                out += [(f.name, n.name) for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = here[: len(here) - node.level + 1] if node.level else []
                mod = ".".join(base + ([node.module] if node.module else []))
                out += [(f.name, mod)] + [(f.name, f"{mod}.{n.name}") for n in node.names]
    return out


def _instinct():
    """One instinct per world (it keeps per-world notes, so two worlds must not share one)."""
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    return hook


def _state(w, drop_memories=False, drop_identity=False):
    d = json.loads(json.dumps(w.to_dict(), sort_keys=True, default=str))
    if drop_identity:  # (two worlds built apart get their own uuid and timeline ids; that isn't physics)
        for k in ("uuid", "epoch", "epochs"):
            d.pop(k, None)
    if drop_memories:
        for a in d["agents"]:
            a.pop("memories", None)
            a.pop("mem_seq", None)
    return d


# ---------------------------------------------------------------- A, L: what the simulation and the minds can see

def test_gate_a_and_l_the_simulation_and_the_minds_never_import_the_lab_or_the_narrator():
    """A: physics can't read a treatment it never imports (the lab keeps who was told in runs/*/treatment.json).
    L: the narrator (chits.story: chronicle, recap, moments, sagas) writes files; nothing in sim/ or brain/ reads it."""
    bad = [(pkg, f, m) for pkg in ("sim", "brain") for f, m in _imports(pkg)
           if m == "chits.lab" or m.startswith(("chits.lab.", "chits.story")) or m in ("chits.tools", "chits.recorder")]
    assert bad == []


# ---------------------------------------------------------------- B: no magic treatment effect

def _claims_only():
    return {"id": "creed", "version": "1", "title": "A synthetic creed", "scope_note": "test only",
            "sources": [{"id": "s1", "citation": "Made up for a test", "edition": "1", "licence": "CC0-1.0"}],
            "claims": [{"id": "c1", "text": "The fire remembers those who feed it.", "category": "belief", "sources": ["s1"]},
                       {"id": "c2", "text": "Share the first catch.", "category": "norm", "sources": ["s1"]}],
            "founders": {"share": 1.0}}


def test_gate_b_the_same_decisions_with_or_without_a_pack_give_identical_physics():
    """Hold the brain's output fixed (here: no plans at all, only the world's own reflexes and rules), and a pack of
    claims changes nothing physical: the told world differs from the untold one only in what its chits remember."""
    told, untold = World("A", "A", 11, "direct", 64, 6), World("A", "A", 11, "direct", 64, 6)
    T.apply(told, _claims_only(), seed=11)
    assert _state(told) != _state(untold)  # (the claims really are in memory)
    for _ in range(TICKS_PER_DAY):
        told.step(lambda w, a: None)
        untold.step(lambda w, a: None)
    assert _state(told, True, True) == _state(untold, True, True)


# ---------------------------------------------------------------- C, D: worldview contract (R8, not built yet)

def _faithful_pair():
    w = World("A", "A", 3, "direct", 64, 4)
    a, b, c, *_ = list(w.agents.values())
    for x in (a, b, c):
        x.x, x.y = 30, 30
    bid = w.found_belief(a, "Way of Fire", "The fire remembers those who feed it")
    assert bid and w.convert(b, bid, "they chose it")
    return w, a, b, c, bid


@pytest.mark.xfail(strict=True, reason="gate C: World._make_child converts a child of two co-believers ('raised'); "
                                       "the strict worldview contract (plan item 50) says children don't inherit beliefs")
def test_gate_c_a_newborn_has_no_worldview_without_exposure():
    w, a, b, _, _ = _faithful_pair()
    home = w.place_site("hut", a.x + 2, a.y, a)
    home.complete, home.needs = True, {}
    child = w._make_child(a, b, home)
    assert child.belief == ""


@pytest.mark.xfail(strict=True, reason="gate D: _do_preach converts a listener by chance (and prayer and reading convert "
                                       "on contact); exposure must be recorded, and only the listener's own decision converts")
def test_gate_d_exposure_is_not_conversion(monkeypatch):
    w, a, _, c, bid = _faithful_pair()
    c.like(a.id, 100)
    monkeypatch.setattr(w, "rng_for", lambda name: type("R", (), {"random": staticmethod(lambda: 0.0)})())
    s = {}
    for _ in range(10):
        if actions._do_preach(w, a, {"do": "preach"}, s) != actions.RUNNING:
            break
    assert bid in c.met_beliefs  # exposed...
    assert c.belief == ""  # ...but nobody decided for it


# ---------------------------------------------------------------- E: the last keeper

def test_gate_e_when_the_last_keeper_dies_nobody_alive_knows_it():
    w = World("A", "A", 5, "direct", 64, 4)
    a = next(iter(w.agents.values()))
    for o in w.agents.values():
        o.knows.pop("recipe:cord", None)
    a.learn("recipe:cord", "discovered", w.tick)
    w.first["recipe:cord"] = {"tick": 0, "by": a.id, "name": a.name}
    w.kill(a, "old age")
    assert "recipe:cord" not in lore.keepers(w)
    assert not any("recipe:cord" in o.knows for o in w.agents.values())  # gone, not quietly kept
    assert any(e.kind == "forgotten" for e in w.events)
    hook = _instinct()
    for _ in range(TICKS_PER_DAY):  # and nothing hands it back without a way it came
        w.step(hook)
    for o in w.agents.values():
        k = o.knows.get("recipe:cord")
        assert k is None or k["how"] in ("discovered", "insight", "read", "observed", "inspected", "taught")


# ---------------------------------------------------------------- F: text lineage (R8, not built yet)

@pytest.mark.xfail(strict=True, reason="gate F: a tablet has no content hash or parent, and reading one records no "
                                       "source (World.learned(..., 'read', None)); there is no copy or retell yet")
def test_gate_f_knowledge_read_from_a_tablet_traces_to_that_tablet():
    w = World("A", "A", 5, "direct", 64, 3)
    a = next(iter(w.agents.values()))
    a.knows.pop("recipe:cord", None)
    tb = Tablet("t1", "recipe:cord", "gone", "an old weaver", w.tick, a.x, a.y, None, "cord is twisted fiber")
    w.tablets[tb.id] = tb
    s = {}
    for _ in range(40):
        if actions._do_read(w, a, {"do": "read", "tablet": tb.id}, s) != actions.RUNNING:
            break
    assert "recipe:cord" in a.knows
    assert a.knows["recipe:cord"]["from"] == tb.id


# ---------------------------------------------------------------- checkpoints: lineages and RNG state

def _checkpointed(days=3):
    """A world run 2 days, a JSON checkpoint of it, and both carried on `days` more days with their own instinct."""
    w = World("A", "A", 8, "direct", 64, 8)
    hook = _instinct()
    for _ in range(2 * TICKS_PER_DAY):
        w.step(hook)
    back = World.from_dict(json.loads(json.dumps(w.to_dict(), default=str)))
    assert _state(back) == _state(w)  # parents, the dead, tablets, beliefs, knowledge sources, RNG state
    hook_back = _instinct()
    for _ in range(days * TICKS_PER_DAY):
        w.step(hook)
        back.step(hook_back)
    return w, back


def _physics(w):
    d = _state(w)
    d.pop("traffic")
    for a in d["agents"]:  # (a step's id is a fresh uuid4 for the observer, not part of the world)
        for s in a.get("plan") or []:
            s.pop("_step_id", None)
    return d


def test_a_checkpoint_carries_on_as_the_world_it_was_taken_from():
    w, back = _checkpointed()
    # everything but traffic (checked exactly below) carries on identically
    assert _physics(back) == _physics(w)


def test_a_checkpoint_keeps_traffic_exactly():
    """Traffic was saved to one decimal, so a restored world's walking costs (traffic over 30 is quicker going) and
    roads drifted from the original's: with the random streams on, seed 8 walked a step slower 129 ticks after."""
    w, back = _checkpointed(days=1)
    assert _state(back)["traffic"] == _state(w)["traffic"]


# ---------------------------------------------------------------- the lab: a run is a function of its protocol

def test_the_same_lab_run_twice_gives_the_same_result(tmp_path):
    proto = ExperimentSpec.from_dict({"name": "twice", "arms": [{"name": "talking"}, {"name": "silent", "culture": "stigmergy"}],
                                      "seeds": [5], "days": 2, "size": 64, "population": 6,
                                      "interventions": [{"day": 2, "kind": "drought"}]}).to_dict()
    arm = {"name": "silent", "culture": "stigmergy", "brain": "instinct", "flags": {}, "treatment": ""}
    one = run.run_one(proto, str(tmp_path / "one"), 5, "B", arm)
    two = run.run_one(proto, str(tmp_path / "two"), 5, "B", arm)
    one.pop("wall_s"), two.pop("wall_s")
    assert one == two
    daily = lambda d: (tmp_path / d / "runs" / "5_B" / "daily.jsonl").read_text()
    assert daily("one") == daily("two")
