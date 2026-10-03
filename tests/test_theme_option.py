"""The theme as an option in the game: the Look button switches between the classic look and Fjordfolk (the Norse
theme) while the world runs. The choice is kept beside the saves, beats CHITS_THEME, and is presentation only: chits
born from then on get the theme's names, chits already named keep theirs, and every observer redraws."""

import asyncio
import json
import os
import random

import pytest

from chits import theme
from chits.sim.agent import _SYL_A, _SYL_B, make_name


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("CHITS_THEME", raising=False)
    theme._chosen = None
    yield
    theme._chosen = None


def test_a_theme_picked_in_the_game_is_kept_and_beats_the_environment(tmp_path, monkeypatch):
    assert theme.active() == "default"
    assert theme.choose("Norse", tmp_path) == "norse" and theme.active() == "norse"
    assert json.loads((tmp_path / theme.THEME_FILE).read_text()) == {"theme": "norse"}
    theme._chosen = None
    theme.load(tmp_path)  # (the next start)
    assert theme.active() == "norse"
    theme.choose("default", tmp_path)
    monkeypatch.setenv("CHITS_THEME", "norse")
    assert theme.active() == "default"  # (picked in the game: the environment only decides until then)
    theme.load(tmp_path / "fresh")  # a data directory with no pick: the environment decides
    assert theme.active() == "norse"
    with pytest.raises(ValueError):
        theme.choose("klingon")


def test_chits_born_after_the_switch_get_norse_names():
    taken = set()
    before = make_name(random.Random(3), taken)
    theme.choose("norse")
    after = make_name(random.Random(3), taken)
    assert after != before and after in theme.norse_names(tuple(_SYL_A), tuple(_SYL_B)).reverse


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


def test_the_look_button_switches_the_running_game_and_every_observer_redraws(env, monkeypatch):
    from fastapi.testclient import TestClient

    from chits.app import R, app

    with TestClient(app) as c:
        rt = R()
        names = {w.id: w.name for w in rt.worlds.values()}
        redrawn = []
        monkeypatch.setattr(rt, "_broadcast_snapshots", lambda: redrawn.append(theme.active()))
        assert c.get("/api/theme").json() == {"theme": "default", "themes": ["default", "norse"]}
        assert c.post("/api/theme", json={"theme": "viking"}).status_code == 400 and not redrawn
        assert c.post("/api/theme", json={"theme": "norse"}).json() == {"ok": True, "theme": "norse"}
        assert redrawn == ["norse"]
        assert c.get("/api/health").json()["theme"] == "norse" and rt.hello()["theme"] == "norse"
        assert {w.id: w.name for w in rt.worlds.values()} == names  # (a world keeps its name)
    assert json.loads((env / theme.THEME_FILE).read_text()) == {"theme": "norse"}
    from chits.runtime import Runtime

    theme._chosen = None
    again = Runtime(env)  # the next start picks the theme up again
    try:
        assert theme.active() == "norse"
    finally:
        asyncio.run(again.mind.close())
        again.store.db.close()
