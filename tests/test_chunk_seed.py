"""Future chunk identity must never collapse distinct coordinate/version tuples."""

from chits.sim.terrain import CHUNK_SEED_SCHEME, chunk_seed


def test_chunk_seed_is_deterministic_and_typed():
    a = chunk_seed(123, 4, -7, 2)
    assert a == chunk_seed(123, 4, -7, 2)
    assert 0 <= a < 2**64
    assert CHUNK_SEED_SCHEME >= 1


def test_chunk_seed_distinguishes_coordinates_sign_and_version():
    base = chunk_seed(123, 4, 7, 2)
    cases = {
        base,
        chunk_seed(123, 7, 4, 2),
        chunk_seed(123, -4, 7, 2),
        chunk_seed(123, 4, -7, 2),
        chunk_seed(123, 4, 7, 3),
        chunk_seed(124, 4, 7, 2),
    }
    assert len(cases) == 6


def test_old_ambiguous_arithmetic_examples_do_not_collide():
    # These tuples all have the same simple arithmetic sum (= 11), but must be distinct identities.
    tuples = [(1, 2, 3, 5), (2, 1, 3, 5), (1, 3, 2, 5), (1, 2, 4, 4)]
    seeds = {chunk_seed(*x) for x in tuples}
    assert len(seeds) == len(tuples)
