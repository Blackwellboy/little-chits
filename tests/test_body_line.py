"""A chit's needs are said in words just before its options when a model chooses: shown only as numbers, every model
benched chose at about chance when the answer was plain (tools/decbench.py)."""

from chits.brain import prompt as P
from chits.brain.instinct import Instinct
from chits.sim.world import World


def _chit():
    w = World("A", "A", 3, "direct", 64, 2)
    a = next(iter(w.agents.values()))
    a.brain = "bench"
    return w, a


def _user(w, a):
    return P.choice_messages(w, a, Instinct().options(w, a))[1]["content"]


def test_a_starving_or_exhausted_chit_is_told_so_just_before_its_options():
    w, a = _chit()
    a.hunger, a.energy, a.warmth, a.health = 4.0, 3.0, 100.0, 100.0
    text = _user(w, a)
    assert "YOUR BODY RIGHT NOW: " in text, text[-600:]
    body = text.split("YOUR BODY RIGHT NOW: ", 1)[1].split("YOUR OPTIONS:", 1)[0]
    assert "starving" in body and "fullness 4 of 100" in body and "Eat now" in body
    assert "exhausted" in body and "Sleep now" in body
    assert text.index("YOUR BODY RIGHT NOW") < text.index("YOUR OPTIONS")


def test_a_chit_already_eating_or_sleeping_on_a_reflex_is_not_told_to_do_it_again():
    # the mind asks for the next plan while the reflex runs: "Eat now" made the model pick a second meal (Codex, #89)
    w, a = _chit()
    a.hunger, a.energy = 4.0, 3.0
    a.plan = [{"do": "eat", "_reflex": True}]
    body = P.body_line(w, a)
    assert "starving" in body and "already getting food" in body and "Eat now" not in body and "Sleep now" in body
    a.plan = [{"do": "sleep", "_reflex": True}]
    body = P.body_line(w, a)
    assert "already going to sleep" in body and "Sleep now" not in body and "Eat now" in body
    a.plan = [{"do": "eat"}]  # a plan the chit chose, not a reflex: still told
    assert "Eat now" in P.body_line(w, a)


def test_a_fed_and_rested_chit_is_told_nothing_is_urgent():
    w, a = _chit()
    a.hunger, a.energy, a.warmth, a.health = 90.0, 90.0, 90.0, 90.0
    assert "YOUR BODY RIGHT NOW: Your body is fine: no urgent needs." in _user(w, a)
    a.hunger, a.energy = 30.0, 25.0
    text = _user(w, a)
    assert "You are hungry (fullness 30 of 100)." in text and "You are tired" in text and "Eat now" not in text
