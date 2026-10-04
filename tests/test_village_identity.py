"""A world that stays one village behaves exactly as it did before projects belonged to villages (F32): the same
random draws in the same order, the same events, the same saved world.

The same seed is run on this tree and on the tree before the change (``git archive`` of BASE into a temp dir), with
tests/identity_runner.py, and the two are compared day by day: a sha256 of the saved world without the uuid labels
and the ``build`` field, with the renamed civic keys put back in their old shape. The one rule of F32 that changes a
one-village world (a lacking building's made materials come first, ``projects.MAKE_FIRST``) is switched off for this
run; tests/test_village_scopes.py covers it on its own.

Skipped where BASE is not in the repository (a shallow clone). ``LC_IDENTITY_DAYS`` runs it longer (default 12).

Opt-in (``LC_IDENTITY=1``) since F32 merged (#81): it proved then that village scoping changes nothing in a
one-village world, and every later change to what instinct does (builders, hoarding) differs from BASE by design,
so in the default suite it could only fail. Run it when a change claims to leave a one-village world alone.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = "0540269"  # main, before one project slot per settlement
RUNNER = Path(__file__).with_name("identity_runner.py")
DAYS = int(os.environ.get("LC_IDENTITY_DAYS", "12"))
pytestmark = pytest.mark.skipif(os.environ.get("LC_IDENTITY") != "1",
                                reason="opt-in: LC_IDENTITY=1 (see the docstring)")


def _run(server: Path, seed: int, culture: str):
    env = dict(os.environ, PYTHONPATH=str(server), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.Popen([sys.executable, str(RUNNER), str(seed), str(DAYS), "128", "18", "0", culture],
                            cwd=server, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


@pytest.fixture(scope="module")
def base_tree(tmp_path_factory):
    git = lambda *a, **kw: subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, **kw)
    if git("cat-file", "-e", f"{BASE}^{{commit}}").returncode:
        pytest.skip(f"{BASE} is not in this clone")
    out = tmp_path_factory.mktemp("base")
    tar = git("archive", BASE, "server")
    assert tar.returncode == 0, tar.stderr
    subprocess.run(["tar", "-x", "-C", str(out)], input=tar.stdout, check=True)
    return out / "server"


@pytest.mark.parametrize("seed,culture", [(42, "direct"), (4, "stigmergy")])
def test_a_one_village_world_is_identical_to_the_tree_before(base_tree, seed, culture):
    procs = [_run(base_tree, seed, culture), _run(ROOT / "server", seed, culture)]
    outs = [p.communicate() for p in procs]
    assert all(p.returncode == 0 for p in procs), [e[-2000:] for _, e in outs]
    before, after = (json.loads(o) for o, _ in outs)
    assert str(base_tree) in before["tree"] and str(ROOT / "server") in after["tree"]  # (each ran its own code)
    assert after["carrying_most"] == 1 == before["carrying_most"], "pick a seed whose world stays one village"
    assert after["projects_done"] > 0, "the run must exercise the projects"
    first = next((i + 1 for i, (x, y) in enumerate(zip(before["daily"], after["daily"])) if x != y), None)
    assert first is None, f"the saved worlds first differ on day {first}"
    assert after["events"] == before["events"] and after["hash"] == before["hash"]
