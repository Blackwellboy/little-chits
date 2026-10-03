"""Names in a long-lived world. Both live worlds ran out of short names by day 2,600 and named every newcomer
"Chit" and a number, and the number (the count of names taken) could come round again."""

import random

from chits.sim.agent import make_name


def test_names_stay_unique_and_chit_like_long_after_the_short_ones_run_out():
    rng, taken = random.Random(7), set()
    for _ in range(6000):
        n = make_name(rng, taken)
        assert n not in taken
        assert not n.startswith("Chit") and len(n) <= 12, n
        taken.add(n)


def test_the_first_names_of_a_world_are_unchanged():
    # (the short names come first, from the same draws as before: seeds keep their founders' names)
    rng, taken = random.Random(42), set()
    first = [make_name(rng, taken) for _ in range(5)]
    assert all(3 <= len(n) <= 7 and n.isalpha() for n in first)


def test_with_every_name_gone_a_numbered_one_is_still_new():
    from chits.sim.agent import _SYL_A, _SYL_B

    taken = {(a + b + v).capitalize() for a in _SYL_A for b in _SYL_B for v in ("", "o", "a", "i", "y")}
    taken |= {(a + a2 + b).capitalize() for a in _SYL_A for a2 in _SYL_A for b in _SYL_B}
    rng = random.Random(3)
    for _ in range(50):
        n = make_name(rng, taken)
        assert n not in taken and n[-1].isdigit(), n
        taken.add(n)


def test_the_longer_names_dont_draw_on_the_callers_stream():
    # for a child the caller's stream is the births stream: hundreds of draws for a longer name moved every trait and
    # lifespan after it (Codex, #19). With the short names gone, the caller's stream moves only as it always did.
    from chits.sim.agent import _SYL_A, _SYL_B

    taken = {(a + b + v).capitalize() for a in _SYL_A for b in _SYL_B for v in ("", "o", "a", "i", "y")}
    rng, replica = random.Random(5), random.Random(5)
    name = make_name(rng, set(taken))
    assert name not in taken
    for _ in range(200):  # (the short-name tries, all taken)
        replica.choice(_SYL_A), replica.choice(_SYL_B)
        if replica.random() < 0.25:
            replica.choice(["o", "a", "i", "y"])
    assert rng.getstate() == replica.getstate()
    assert make_name(random.Random(99), set(taken)) == name  # (and it doesn't depend on that stream)
