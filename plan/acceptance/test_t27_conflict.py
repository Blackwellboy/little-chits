from chits.brain import prompt as P
from chits.sim.world import World


def setup(seed=3, n=3):
    w = World("A", "A", seed, "direct", 96, n)
    ags = list(w.agents.values())
    for a in ags:
        a.born = -240 * 10
        a.hunger = a.energy = a.warmth = a.health = 100.0
        a.inventory.clear()
        a.plan = []
    owner = ags[0]
    pos = w.find_site("stockpile", owner.x, owner.y)
    st = w.place_site("stockpile", pos[0], pos[1], owner)
    w.complete_structure(st, owner)
    st.storage = {"bread": 10}
    return w, ags, st


def run(w, a, step, limit=200):
    a.plan = [dict(step)]
    for _ in range(limit):
        w.step()
        if not a.plan:
            break
    return a.last_result


def far_away(w, a, st, d=20):
    for dx in range(d, d + 15):
        x = min(w.w - 1, st.x + dx)
        if w.passable(x, st.y):
            a.x, a.y = x, st.y
            return
    raise AssertionError("no far spot")


def test_theft_and_grudge():
    w, (owner, thief, *_), st = setup()
    evs = []
    w.listeners.append(evs.append)
    far_away(w, owner, st)
    owner.affinity[thief.id] = 30.0
    run(w, thief, {"do": "steal", "target": st.id, "what": "bread", "qty": 3})
    assert thief.inventory.get("bread") == 3 and st.storage.get("bread") == 7, thief.last_result
    assert owner.affinity[thief.id] <= 5.0 + 1e-6 + 3  # a big grudge (company may add a little)
    assert any(e.kind == "theft" for e in evs)
    assert "own" in run(w, owner, {"do": "steal", "target": st.id, "what": "bread"}).lower()


def test_guards_catch_thieves():
    w, (owner, thief, guard), st = setup(5)
    evs = []
    w.listeners.append(evs.append)
    far_away(w, owner, st)
    guard.x, guard.y = st.x, st.y
    guard.plan = [{"do": "guard", "target": st.id, "qty": 240}]
    for _ in range(3):
        w.step()
    assert guard.activity == "guarding"
    run(w, thief, {"do": "rob", "target": st.id, "what": "bread"})
    assert not thief.inventory.get("bread") and st.storage.get("bread") == 10
    assert thief.health <= 91
    assert any(e.kind == "caught" for e in evs)


def test_fights_hurt_but_never_kill():
    w, (a, b, c), st = setup(7)
    b.x, b.y = a.x, a.y
    for _ in range(12):
        a.health = b.health = 100.0
        run(w, a, {"do": "fight", "to": b.name}, limit=40)
    assert min(a.health, b.health) >= 5
    a.health = b.health = 6.0
    run(w, a, {"do": "attack", "to": b.name}, limit=40)
    assert a.alive and b.alive and min(a.health, b.health) >= 5 - 1e-6
    assert a.affinity.get(b.id, 0) < 0
    assert '"do":"steal"' in P.verb_guide(w).replace(" ", "")


def test_militia():
    w, ags, st = setup(9, n=6)
    evs = []
    w.listeners.append(evs.append)
    for a in ags[:4]:
        a.job, a.job_source = "guard", "chosen"
    for _ in range(240):
        w.step()
    assert w.stats()["guards"] == 4
    assert any(e.kind == "militia" and "guard of 4" in e.text for e in evs)
