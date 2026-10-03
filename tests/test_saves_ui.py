"""💾 Saves in the main UI: the god-mode save points, listed with their day, population and era, loaded with the same
restore (the run is marked modified, a new timeline starts), and one save as one file to export and import. Play games
only: an experiment refuses every one of these routes. An imported file is untrusted input."""

import gzip
import json
import os

import pytest


@pytest.fixture
def env(monkeypatch, tmp_path):
    for key in tuple(os.environ):
        if key.startswith("CHITS_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CHITS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHITS_AUTODETECT", "0")
    monkeypatch.setenv("CHITS_SPEED", "0")
    monkeypatch.setenv("CHITS_WORLD_SIZE", "64")
    monkeypatch.setenv("CHITS_PER_WORLD", "6")
    monkeypatch.setenv("CHITS_MODE", "versus")
    return tmp_path


def client():
    from fastapi.testclient import TestClient

    from chits.app import app

    return TestClient(app)


def rt():
    from chits.app import R

    return R()


def test_a_save_is_listed_with_its_day_population_and_era_then_loaded_as_a_new_timeline(env):
    with client() as c:
        r = rt()
        r.step_worlds(30)
        made = c.post("/api/saves", json={"name": "before the storm"}).json()
        assert made["name"] == "before the storm" and made["tick"] == 30
        assert (made["day"], made["population"], made["era"]) == (1, 12, "Wanderers")
        assert made["worlds"]["A"]["population"] == 6 and made["created"] > 0
        assert c.get("/api/saves").json()["saves"][0] == made
        # god mode's list is the same save, in the shape it always had
        assert c.get("/api/savepoints").json() == [{k: made[k] for k in ("id", "name", "created", "tick")}]

        r.step_worlds(40)
        epochs = {wid: w.epoch for wid, w in r.worlds.items()}
        assert c.get("/api/run").json()["sandbox_modified"] is False
        got = c.post(f"/api/saves/{made['id']}/load")
        assert got.status_code == 200 and got.json()["ok"] and got.json()["control"]["sandbox_modified"] is True
        for wid, w in r.worlds.items():
            assert w.tick == 30 and w.epoch != epochs[wid]  # back at the save, in a new timeline
            assert w.epochs[-1]["parent"] == epochs[wid]
            assert any(e.kind == "timeline" and "before the storm" in e.text for e in w.events)
        run = c.get("/api/run").json()
        assert run["sandbox_modified"] is True and run["sandbox_reasons"] == ["restored save point before the storm"]

        assert c.post("/api/saves/999/load").status_code == 404
        assert c.delete(f"/api/saves/{made['id']}").status_code == 200
        assert c.get("/api/saves").json() == {"saves": []}
        assert c.delete(f"/api/saves/{made['id']}").status_code == 404


def test_a_save_made_before_summaries_were_kept_still_lists_its_day_population_and_era(env):
    with client() as c:
        r = rt()
        r.step_worlds(5)
        sid = r.store.save_point("old", 5, {wid: w.to_dict() for wid, w in r.worlds.items()})  # (no summary)
        row = c.get("/api/saves").json()["saves"][0]
        assert (row["id"], row["day"], row["population"], row["era"]) == (sid, 1, 12, "Wanderers")
        assert r.store.db.execute("SELECT summary FROM savepoints WHERE id=?", (sid,)).fetchone()[0]  # kept, once


def test_a_save_exports_as_one_file_and_imports_as_a_new_save(env):
    with client() as c:
        r = rt()
        r.step_worlds(20)
        made = c.post("/api/saves", json={"name": "day one / A*"}).json()
        out = c.get(f"/api/saves/{made['id']}/export")
        assert out.status_code == 200 and out.headers["content-type"] == "application/gzip"
        assert out.headers["content-disposition"] == 'attachment; filename="little-chits-day-one---A.lcsave"'
        doc = json.loads(gzip.decompress(out.content))
        assert (doc["format"], doc["version"], doc["name"], doc["tick"]) == ("little-chits-save", 1, "day one / A*", 20)
        assert set(doc["worlds"]) == {"A", "B"} and doc["worlds"]["A"]["uuid"] == r.worlds["A"].uuid

        sandbox = c.get("/api/run").json()["sandbox_modified"]  # (this writes the run's manifest)
        before = sorted(p.name for p in env.rglob("*") if p.is_file())
        got = c.post("/api/saves/import", content=out.content)
        assert got.status_code == 200
        new = got.json()
        assert new["id"] != made["id"] and new["imported"] is True and new["name"] == "day one / A*"
        assert (new["day"], new["population"], new["era"], new["tick"]) == (1, 12, "Wanderers", 20)
        assert [s["id"] for s in c.get("/api/saves").json()["saves"]] == [new["id"], made["id"]]
        assert r.store.load_save_point(new["id"])["worlds"] == r.store.load_save_point(made["id"])["worlds"]
        # importing changes no world and marks nothing: only the database gained a row
        assert c.get("/api/run").json()["sandbox_modified"] is sandbox and r.worlds["A"].tick == 20
        assert sorted(p.name for p in env.rglob("*") if p.is_file()) == before
        # the plain JSON of the same file imports too
        assert c.post("/api/saves/import", content=gzip.decompress(out.content)).status_code == 200

        # loading the imported save is the same restore, and the run's record says where the world came from
        r.step_worlds(10)
        assert c.post(f"/api/saves/{new['id']}/load").status_code == 200
        assert r.worlds["A"].tick == 20
        assert c.get("/api/run").json()["sandbox_reasons"] == [
            "restored save point day one / A*", "save point day one / A* came from an imported file"]


def test_a_file_that_is_not_a_readable_save_is_refused_and_nothing_is_kept(env, monkeypatch):
    with client() as c:
        r = rt()
        made = c.post("/api/saves", json={"name": "ok"}).json()
        good = json.loads(gzip.decompress(c.get(f"/api/saves/{made['id']}/export").content))

        def variant(**change):
            doc = json.loads(json.dumps(good))
            doc.update(change)
            return json.dumps(doc).encode()

        def world(**change):
            doc = json.loads(json.dumps(good))
            doc["worlds"]["A"].update(change)
            return json.dumps(doc).encode()

        bad = {
            "not JSON": (b"\x00\x01 pickle? no", "not a Little Chits save"),
            "a list": (b"[1, 2, 3]", "not a Little Chits save"),
            "another format": (variant(format="something-else"), "not a Little Chits save"),
            "a newer file version": (variant(version=2), "version 2; this build reads version 1"),
            "a version that is not a number": (variant(version="1"), "this build reads version 1"),
            "no worlds": (variant(worlds={}), "holds no worlds"),
            "a path for a world id": (variant(worlds={"../../x": good["worlds"]["A"]}), "holds no worlds"),
            "a world under the wrong id": (variant(worlds={"A": good["worlds"]["B"]}), "World A"),
            "a newer snapshot schema": (world(schema=99), "can't be read by this build"),
            "a huge island": (world(size=10 ** 6), "World A"),
            "a world that does not load": (world(agents=[{"nope": 1}]), "can't be read by this build"),
            "damaged gzip": (b"\x1f\x8b" + b"junk" * 20, "could not be unpacked"),
        }
        for what, (body, reason) in bad.items():
            got = c.post("/api/saves/import", content=body)
            assert got.status_code == 400 and reason in got.json()["detail"], (what, got.text)
        # too big as sent, and too big once unpacked (a small file that unpacks to a huge one)
        monkeypatch.setattr(r, "SAVE_FILE_MAX", 2000)
        assert c.post("/api/saves/import", content=b" " * 2001).status_code == 413
        monkeypatch.setattr(r, "SAVE_JSON_MAX", 5000)
        bomb = gzip.compress(b" " * 200_000)
        assert len(bomb) < 2000
        got = c.post("/api/saves/import", content=bomb)
        assert got.status_code == 400 and "unpacks to more" in got.json()["detail"]
        assert [s["id"] for s in c.get("/api/saves").json()["saves"]] == [made["id"]]


def test_an_imported_world_must_be_whole_and_able_to_run_before_it_is_kept(env, monkeypatch):
    """Codex on PR #72: a snapshot with a short per-tile list loads (from_dict copies it) and then crashes the first
    step that looks at that tile. Refused at import: the lists cover the map, everything stands on it, and a
    throwaway copy runs a few ticks."""
    with client() as c:
        r = rt()
        r.step_worlds(10)
        made = c.post("/api/saves", json={"name": "ok"}).json()
        good = json.loads(gzip.decompress(c.get(f"/api/saves/{made['id']}/export").content))

        def broken(change):
            doc = json.loads(json.dumps(good))
            change(doc["worlds"]["B"])
            return json.dumps(doc).encode()

        def off_map(key):
            def change(w):
                w[key][0]["x"] = 10 ** 6
            return change

        bad = {
            "no paths at all": (lambda w: w.update(traffic=[]), "paths do not cover the 64 by 64 map"),
            "paths cut short": (lambda w: w.update(traffic=w["traffic"][:100]), "paths do not cover"),
            "resource amounts cut short": (lambda w: w.update(res_amt=w["res_amt"][:-1]), "resource amounts do not cover"),
            "a resource amount that is no number": (lambda w: w["res_amt"].__setitem__(5, "lots"), "resource amounts"),
            "a road off the map": (lambda w: w.update(roads=[64 * 64]), "a road or tunnel is off the map"),
            "a chit off the map": (off_map("agents"), "a chit is off the map"),
            "an animal off the map": (lambda w: w.update(animals={"n1": {"id": "n1", "kind": "sheep", "x": -3, "y": 2}}),
                                      "an animal is off the map"),
            "a pile off the map": (lambda w: w.update(ground={"900,2": {"wood": 1}}), "a pile on the ground is off the map"),
        }
        for what, (change, reason) in bad.items():
            got = c.post("/api/saves/import", content=broken(change))
            assert got.status_code == 400 and "World B" in got.json()["detail"] and reason in got.json()["detail"],                 (what, got.text)
        assert [s["id"] for s in c.get("/api/saves").json()["saves"]] == [made["id"]]

        # the copy that is tried is thrown away: the worlds running, and the snapshot kept, are untouched by the trial
        before = {wid: (w.tick, w.seq) for wid, w in r.worlds.items()}
        new = c.post("/api/saves/import", content=json.dumps(good).encode()).json()
        assert r.store.load_save_point(new["id"])["worlds"] == good["worlds"]
        assert {wid: (w.tick, w.seq) for wid, w in r.worlds.items()} == before

        # a world that loads and is whole but cannot take a step is refused too
        from chits.sim.world import World

        steps = []

        def stuck(self, hook):
            steps.append(self.id)
            raise KeyError("no such design")

        with monkeypatch.context() as m:
            m.setattr(World, "step", stuck)
            got = c.post("/api/saves/import", content=json.dumps(good).encode())
        assert got.status_code == 400 and "loads but can't run" in got.json()["detail"] and steps == ["A"]


def test_a_save_with_other_worlds_than_this_game_is_not_loaded(env):
    with client() as c:
        r = rt()
        r.step_worlds(10)
        made = c.post("/api/saves", json={"name": "two"}).json()
        doc = json.loads(gzip.decompress(c.get(f"/api/saves/{made['id']}/export").content))
        del doc["worlds"]["B"]
        one = c.post("/api/saves/import", content=json.dumps(doc).encode()).json()
        assert one["population"] == 6 and list(one["worlds"]) == ["A"]
        r.step_worlds(10)
        epoch = r.worlds["A"].epoch
        got = c.post(f"/api/saves/{one['id']}/load")
        assert got.status_code == 409 and "holds 1 world and this game has 2" in got.json()["detail"]
        assert r.worlds["A"].tick == 20 and r.worlds["A"].epoch == epoch
        assert c.get("/api/run").json()["sandbox_modified"] is False


def test_an_experiment_run_refuses_every_saves_route_and_says_why(env):
    with client() as c:
        r = rt()
        made = c.post("/api/saves", json={"name": "play"}).json()
        blob = c.get(f"/api/saves/{made['id']}/export").content
        r.step_worlds(10)
        r.contract = "experiment"
        try:
            ticks = {wid: (w.tick, w.epoch) for wid, w in r.worlds.items()}
            calls = [c.get("/api/saves"), c.post("/api/saves", json={"name": "x"}),
                     c.post(f"/api/saves/{made['id']}/load"), c.get(f"/api/saves/{made['id']}/export"),
                     c.post("/api/saves/import", content=blob), c.delete(f"/api/saves/{made['id']}")]
            for got in calls:
                assert got.status_code == 409 and "experiment" in got.json()["detail"], got.text
            assert {wid: (w.tick, w.epoch) for wid, w in r.worlds.items()} == ticks
            assert len(r.store.save_points()) == 1 and r.store.get_meta("sandbox_modified") != "1"
        finally:
            r.contract = "play"


def test_the_saves_routes_need_the_access_token_like_every_private_route(env, monkeypatch):
    with client() as c:
        monkeypatch.setenv("CHITS_TOKEN", "sesame-for-this-test")
        assert c.get("/api/saves").status_code == 401
        assert c.post("/api/saves", json={"name": "x"}).status_code == 401
        assert c.post("/api/saves/import", content=b"{}").status_code == 401
        assert c.get("/api/saves/1/export").status_code == 401
        ok = {"Authorization": "Bearer sesame-for-this-test"}
        assert c.get("/api/saves", headers=ok).json() == {"saves": []}
        monkeypatch.delenv("CHITS_TOKEN")
