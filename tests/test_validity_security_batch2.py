"""Regression gates for audit batch 2: F8, F18, F21, F23."""

import asyncio
import json

import pytest
from pathlib import Path

from chits import diag
from chits.runtime import Runtime, legacy_brains_warning
from chits.sim.world import RNG_SCHEME, World


def test_condition_specific_rng_cannot_move_shared_weather_damage():
    a = World("A", "A", 41, "direct", 64, 0)
    b = World("B", "B", 41, "direct", 64, 0)
    # These are arm-specific or optional systems. Extra activity in one world must not move an exogenous stream.
    for domain in ("beliefs", "combat", "artifacts", "god"):
        for _ in range(40):
            a.rng_for(domain).random()
    assert a.rng.random() == b.rng.random()  # legacy .rng is reserved for shared weather damage
    assert a.rng_for("weather").random() == b.rng_for("weather").random()

    snap = a.to_dict()
    assert snap["rng_scheme"] == RNG_SCHEME == 3  # (streams per system, thing and tick: tests/test_rng_streams.py)
    restored = World.from_dict(json.loads(json.dumps(snap)))
    assert restored.to_dict()["rng_scheme"] == RNG_SCHEME
    assert restored.rng_for("beliefs").random() == a.rng_for("beliefs").random()


def test_no_condition_specific_module_uses_the_legacy_rng_alias():
    root = Path(__file__).resolve().parents[1]
    for rel in ("server/chits/sim/actions.py", "server/chits/sim/artifacts.py", "server/chits/runtime.py"):
        text = (root / rel).read_text()
        assert "world.rng." not in text, rel
        assert "w.rng." not in text, rel


def test_play_scorecard_says_it_is_not_a_controlled_comparison(tmp_path):
    rt = Runtime(tmp_path)
    sc = diag.scorecard(rt)
    assert sc["controlled"] is False
    assert "not a controlled comparison" in sc["warning"].lower()
    rt.contract = "experiment"
    sc = diag.scorecard(rt)
    assert sc["controlled"] is True and sc["warning"] == ""
    rt.store.db.close()
    asyncio.run(rt.mind.close())


def test_private_api_reads_need_the_token_but_health_stays_a_liveness_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_PER_WORLD", "3")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_TOKEN", "read-secret")
    monkeypatch.delenv("CHITS_MODEL_URL", raising=False)
    from fastapi.testclient import TestClient
    from chits.app import app

    with TestClient(app) as c:
        assert c.get("/api/health").status_code == 200  # no world detail beyond tick/population
        assert c.get("/api/worlds").status_code == 401
        assert c.get("/api/run").status_code == 401
        h = {"Authorization": "Bearer read-secret"}
        assert c.get("/api/worlds", headers=h).status_code == 200
        assert c.get("/api/run", headers=h).status_code == 200


def test_legacy_brains_file_is_explicitly_ignored(tmp_path):
    live = tmp_path / "server" / "data" / "brains.json"
    live.parent.mkdir(parents=True)
    live.write_text("{}")
    legacy = tmp_path / "brains.local.json"
    legacy.write_text("{}")
    warning = legacy_brains_warning(live, tmp_path)
    assert "ignoring legacy" in warning and str(live) in warning
    legacy.unlink()
    assert legacy_brains_warning(live, tmp_path) == ""


def test_unknown_rng_scheme_is_refused_and_manifest_records_current_scheme(tmp_path):
    from chits.runtime import Runtime
    from chits.sim.world import RNG_SCHEME, World

    w = World("A", "A", 7, "direct", 64, 2)
    snap = w.to_dict()
    snap["rng_scheme"] = RNG_SCHEME + 99
    with pytest.raises(ValueError, match="unsupported RNG scheme"):
        World.from_dict(snap)

    rt = Runtime(tmp_path)
    assert rt.manifest()["rng_scheme"] == RNG_SCHEME
    rt.store.db.close()
    asyncio.run(rt.mind.close())
