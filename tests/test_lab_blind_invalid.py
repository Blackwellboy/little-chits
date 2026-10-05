"""An invalid run must not unblind the report (Codex on #122). `brain_unavailable` says which model stopped
answering, so its text names the brain. Everything the blind report and the CLI read about an invalid run is
redacted to the blind label. The raw record goes to invalid-sealed.json, which only an unblinded report reads, and it
keeps every break, however many there were."""

import json
import socket
import threading
import time

import pytest

from chits import invariants as INV
from chits.lab import report, run
from chits.lab.__main__ import main as lab_main
from chits.sim.agent import TICKS_PER_DAY

LABEL, MODEL, BRAIN, ARM = "Secretmodel Nine", "secretmodel-9b-Q8_0.gguf", "secretbrain", "secretarm"


@pytest.fixture(scope="module")
def secret_server():
    """A fake model server that lists the secret model's name (its latency is set per test)."""
    import uvicorn
    import fake_llm as F

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    old = (F.STATE.get("latency"), F.STATE.get("models"))
    F.STATE["models"] = ["fake-chit-7b", "fake", MODEL]
    server = uvicorn.Server(uvicorn.Config(F.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    F.STATE["latency"] = old[0] if old[0] is not None else 0.005
    if old[1] is None:
        F.STATE.pop("models", None)
    else:
        F.STATE["models"] = old[1]


@pytest.fixture
def slow_fake(secret_server):
    """Slower than the brain will wait: every call times out."""
    import fake_llm as F

    F.STATE["latency"] = 0.4
    yield secret_server
    F.STATE["latency"] = 0.005


@pytest.fixture
def fake_fast(secret_server):
    import fake_llm as F

    F.STATE["latency"] = 0.002
    yield secret_server


def _blind_files(out):
    """Everything blind: the report, its CSVs, and each run's invalid.json (what the report and the CLI read)."""
    files = list(out.glob("*-blind.*")) + list(out.glob("runs/*/invalid.json"))
    assert files
    return {f.name: f.read_text() for f in files}


def _secrets(url):
    """The arm's identities and their common spellings: the label and its words, the model file with and without its
    extension, the brain id, the arm's name, the URL with and without its scheme and trailing slash, host:port."""
    host = url.split("//", 1)[1].split("/", 1)[0]
    return [LABEL, *LABEL.split(), MODEL, MODEL.rsplit(".", 1)[0], BRAIN, ARM, url, url + "/", url.split("//", 1)[1],
            host]


def _assert_blind(texts, url):
    """No identity appears in any of `texts`, in any case (whole words: 'Nine' must not hide in 'nineteen')."""
    import re

    for where, text in texts.items():
        for s in _secrets(url):
            hit = re.search(f"(?<![A-Za-z0-9_]){re.escape(s)}(?![A-Za-z0-9_])", text, re.IGNORECASE)
            assert not hit, f"{s!r} (as {hit.group(0)!r}) in {where}"


def _variants(url):
    """The same identities as a server, a client and a log might spell them."""
    host = url.split("//", 1)[1].split("/", 1)[0]
    return (f"{LABEL.upper()} stopped; {LABEL.lower()} again; {LABEL.split()[0].lower()} said so; "
            f"model {MODEL.lower()} ({MODEL.rsplit('.', 1)[0].upper()}); brain {BRAIN.upper()} of {ARM.title()}; "
            f"at {url.upper()}/ and {url.split('//', 1)[1].lower()} via {host.upper()}")


def test_case_variants_and_normalised_spellings_are_redacted(fake_fast, tmp_path, monkeypatch, capsys):
    """A break or a model call can spell the arm's identities in any case (a server lower-cases the model, a client
    normalises the host): the blind record names none of them, whatever the spelling."""
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    real = INV.check
    said = _variants(fake_fast)

    def fake(world, contract="play", world_brain=None):
        found = real(world, contract, world_brain)
        if world.tick >= 10:
            found.append({"kind": "negative_stock", "level": "hard", "tick": world.tick, "what": said})
        return found

    monkeypatch.setattr(INV, "check", fake)
    brain = {"id": BRAIN, "label": LABEL, "base_url": fake_fast, "model": MODEL, "max_concurrency": 4,
             "max_tokens": 100}
    proto = {"name": "blind", "arms": [{"name": ARM, "brain": BRAIN}, {"name": "baseline"}], "allow_models": True,
             "brains": {BRAIN: brain}, "seeds": [3], "days": 1, "size": 64, "population": 4}
    (tmp_path / "p.json").write_text(json.dumps(proto))
    out = tmp_path / "out"
    assert lab_main(["run", str(tmp_path / "p.json"), "--out", str(out)]) == 3
    cli = capsys.readouterr()
    report.write_pack(out)
    _assert_blind({"cli": cli.out + cli.err, **_blind_files(out)}, fake_fast)
    sealed = [json.loads(p.read_text()) for p in out.glob("runs/*/invalid-sealed.json")]
    assert any(said in json.dumps(s) for s in sealed)  # (word for word, sealed)


def test_a_legacy_raw_record_is_migrated_before_anything_blind_reads_it(fake_fast, tmp_path, monkeypatch, capsys):
    """A run invalidated by the previous version left only a raw invalid.json (with the arm, its brain and the
    model's name). The first analyze or resume moves it to invalid-sealed.json, writes the redacted invalid.json,
    and says it did."""
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    brain = {"id": BRAIN, "label": LABEL, "base_url": fake_fast, "model": MODEL, "max_concurrency": 4,
             "max_tokens": 100}
    proto = {"name": "blind", "arms": [{"name": ARM, "brain": BRAIN}, {"name": "baseline"}], "allow_models": True,
             "brains": {BRAIN: brain}, "seeds": [3, 4], "days": 1, "size": 64, "population": 4}
    from chits.lab.spec import ExperimentSpec

    spec = ExperimentSpec.from_dict(proto)
    out = tmp_path / "out"
    run.start(spec, out)
    names = json.loads((out / "sealed" / "assignment.json").read_text())
    label = next(l for l, n in names.items() if n == ARM)
    legacy = {"seed": 3, "label": label, "arm": ARM, "brain": BRAIN, "kind": "brain_unavailable",
              "what": f"{LABEL}: 12 requests failed in a row", "tick": 40, "day": 1,
              "broken": [{"kind": "brain_unavailable", "level": "hard", "tick": 40,
                          "what": f"{LABEL}: 12 requests failed in a row"}],
              "wall_s": 1.0, "tape_calls": 12,
              "last_calls": [{"n": 11, "error": f"ReadTimeout: {fake_fast.lower()}/chat/completions", "text": None}]}
    legacy_attempt = dict(legacy, what=f"{MODEL}: down")
    for seed, rec, name in ((3, legacy, "invalid.json"), (4, legacy_attempt, "invalid-attempt-1.json")):
        rd = out / "runs" / f"{seed}_{label}"
        rd.mkdir(parents=True)
        (rd / name).write_text(json.dumps(dict(rec, seed=seed)))

    report.write_pack(out)  # the first blind read migrates
    rd = out / "runs" / f"3_{label}"
    sealed = json.loads((rd / "invalid-sealed.json").read_text())
    assert sealed["arm"] == ARM and LABEL in sealed["what"] and sealed["migrated"]  # the raw record, kept
    blind = json.loads((rd / "invalid.json").read_text())
    assert blind["migrated"] and "arm" not in blind and blind["what"].startswith(f"arm {label}")
    assert json.loads((out / "runs" / f"4_{label}" / "invalid-sealed-attempt-1.json").read_text())["arm"] == ARM
    assert run.attempts(out / "runs" / f"4_{label}") == 1  # (an attempt is still counted once)
    _assert_blind(_blind_files(out) | {"attempt": (out / "runs" / f"4_{label}" / "invalid-attempt-1.json").read_text()},
                  fake_fast)
    assert LABEL in report.write_pack(out, unblind=True).read_text()

    # the command line's listing reads only the blind records, and a resume migrates too
    (rd / "invalid-sealed.json").unlink()
    (rd / "invalid.json").write_text(json.dumps(legacy))
    assert lab_main(["resume", str(out)]) == 3
    cli = capsys.readouterr()
    _assert_blind({"cli": cli.out + cli.err}, fake_fast)
    assert json.loads((rd / "invalid-sealed.json").read_text())["arm"] == ARM


def test_an_invalid_model_run_names_no_model_in_anything_blind(slow_fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    brain = {"id": BRAIN, "label": LABEL, "base_url": slow_fake, "model": MODEL, "max_concurrency": 4,
             "timeout": 0.05, "max_tokens": 100}
    proto = {"name": "blind", "arms": [{"name": ARM, "brain": BRAIN}, {"name": "baseline"}], "allow_models": True,
             "brains": {BRAIN: brain}, "seeds": [3], "days": 1, "size": 64, "population": 4}
    (tmp_path / "p.json").write_text(json.dumps(proto))
    out = tmp_path / "out"
    assert lab_main(["run", str(tmp_path / "p.json"), "--out", str(out), "--jobs", "2"]) == 3
    cli = capsys.readouterr()
    assert "brain_unavailable" in cli.err
    report.write_pack(out)
    _assert_blind({"cli": cli.out + cli.err, **_blind_files(out)}, slow_fake)
    bad = json.loads(next(out.glob("runs/*/invalid.json")).read_text())
    assert bad["kind"] == "brain_unavailable" and "12 requests failed in a row" in bad["what"]
    assert bad["what"].startswith(f"arm {bad['label']}")  # (named by its blind label instead)
    # the raw record is kept, sealed, and only the unblinded report shows it
    sealed = json.loads(next(out.glob("runs/*/invalid-sealed.json")).read_text())
    assert sealed["arm"] == ARM and sealed["brain"] == BRAIN and LABEL in sealed["what"]
    assert all("Timeout" in (c["error"] or "") for c in sealed["last_calls"])
    assert LABEL in report.write_pack(out, unblind=True).read_text()


def test_every_break_is_kept_however_many(tmp_path, monkeypatch):
    real = INV.check

    def fake(world, contract="play", world_brain=None):
        found = real(world, contract, world_brain)
        if world.tick >= TICKS_PER_DAY:
            found += [{"kind": "negative_stock", "level": "hard", "tick": world.tick, "what": f"c{i} holds -1 wood"}
                      for i in range(25)]
        return found

    monkeypatch.setattr(INV, "check", fake)
    from chits.lab.spec import ExperimentSpec

    spec = ExperimentSpec.from_dict({"name": "many", "arms": [{"name": "p"}, {"name": "q"}], "seeds": [3], "days": 2,
                                     "size": 64, "population": 4})
    run.run(spec, tmp_path)
    for rd in (tmp_path / "runs").glob("*_*"):
        bad = json.loads((rd / "invalid.json").read_text())
        sealed = json.loads((rd / "invalid-sealed.json").read_text())
        assert bad["breaks"] == 25 and bad["by_kind"] == {"negative_stock": 25}
        assert len(sealed["broken"]) == 25 and sealed["broken"][-1]["what"] == "c24 holds -1 wood"


def test_arms_named_like_blind_labels_keep_their_own_label(tmp_path, monkeypatch):
    """Arms named "A" and "B", sealed crosswise (arm "B" is label A): the structural label is never rewritten, and the
    break's text names each arm by its own label."""
    from chits.lab import assign
    from chits.lab.spec import ExperimentSpec

    def proto(k):
        return {"name": "crossed", "arms": [{"name": "A"}, {"name": "B", "culture": "stigmergy"}], "seeds": [3],
                "days": 2, "size": 64, "population": 4, "assign_seed": k}

    k = next(k for k in range(50) if assign.labels(ExperimentSpec.from_dict(proto(k)))["A"] == "B")
    spec = ExperimentSpec.from_dict(proto(k))
    real = INV.check

    def fake(world, contract="play", world_brain=None):
        found = real(world, contract, world_brain)
        if world.tick >= TICKS_PER_DAY:
            found.append({"kind": "negative_stock", "level": "hard", "tick": world.tick, "what": "A took B's wood"})
        return found

    monkeypatch.setattr(INV, "check", fake)
    run.run(spec, tmp_path)
    for rd in (tmp_path / "runs").glob("*_*"):
        label = rd.name.split("_")[1]
        bad = json.loads((rd / "invalid.json").read_text())
        assert bad["label"] == label  # (never "arm B", never the other arm's)
        assert bad["what"] == "arm B took arm A's wood"  # arm "A" is label B, arm "B" is label A
    text = report.write_pack(tmp_path).read_text()
    assert "| 3 | A | 2 |" in text and "| 3 | B | 2 |" in text


def test_a_model_the_server_chose_is_redacted_too(secret_server, tmp_path, monkeypatch):
    """A brain with no `model` runs the first one its server lists (LLMBrain.resolve_model), and its label falls back
    to that name. That name is recorded (server.json) and redacted like the configured ones."""
    import fake_llm as F

    chosen = "Hiddenpick-7b-Q4_K_M.gguf"
    F.STATE["models"] = [chosen, "fake-chit-7b", "fake", MODEL]
    F.STATE["latency"] = 0.002
    monkeypatch.setenv("CHITS_LAB_ALLOW_MODELS", "1")
    real = INV.check

    def fake(world, contract="play", world_brain=None):
        found = real(world, contract, world_brain)
        if world.tick >= 10:
            found.append({"kind": "negative_stock", "level": "hard", "tick": world.tick,
                          "what": f"{chosen.lower()} said {chosen.rsplit('.', 1)[0].upper()}"})
        return found

    monkeypatch.setattr(INV, "check", fake)
    from chits.lab.spec import ExperimentSpec

    spec = ExperimentSpec.from_dict({"name": "chosen", "arms": [{"name": ARM, "brain": BRAIN}, {"name": "baseline"}],
                                     "allow_models": True, "seeds": [3], "days": 1, "size": 64, "population": 4,
                                     "brains": {BRAIN: {"id": BRAIN, "base_url": secret_server, "model": "",
                                                        "max_concurrency": 4, "max_tokens": 100}}})
    try:
        run.run(spec, tmp_path)
    finally:
        F.STATE["models"] = ["fake-chit-7b", "fake", MODEL]
    served = json.loads(next(tmp_path.glob("runs/*/server.json")).read_text())
    assert served["resolved_model"] == chosen
    report.write_pack(tmp_path)
    for where, text in _blind_files(tmp_path).items():
        for s in (chosen, chosen.rsplit(".", 1)[0], "Hiddenpick"):
            assert s.lower() not in text.lower(), f"{s!r} in {where}"


def test_a_migration_stopped_between_its_two_writes_is_finished_blind(fake_fast, tmp_path):
    """Codex on #123 (issue #125): the sealed copy was written, then the process stopped before the public record was
    redacted. The next migration saw the sealed copy and skipped the record, so invalid.json stayed raw for good."""
    brain = {"id": BRAIN, "label": LABEL, "base_url": fake_fast, "model": MODEL, "max_concurrency": 4,
             "max_tokens": 100}
    proto = {"name": "blind", "arms": [{"name": ARM, "brain": BRAIN}, {"name": "baseline"}], "allow_models": True,
             "brains": {BRAIN: brain}, "seeds": [3], "days": 1, "size": 64, "population": 4}
    from chits.lab.spec import ExperimentSpec

    out = tmp_path / "out"
    run.start(ExperimentSpec.from_dict(proto), out)
    names = json.loads((out / "sealed" / "assignment.json").read_text())
    label = next(l for l, n in names.items() if n == ARM)
    legacy = {"seed": 3, "label": label, "arm": ARM, "brain": BRAIN, "kind": "brain_unavailable",
              "what": f"{LABEL}: 12 requests failed in a row", "tick": 40, "day": 1,
              "broken": [{"kind": "brain_unavailable", "level": "hard", "tick": 40, "what": f"{MODEL} down"}]}
    rd = out / "runs" / f"3_{label}"
    rd.mkdir(parents=True)
    sealed = dict(legacy, migrated={"at": "then", "from": "invalid.json", "note": "first write"})
    (rd / "invalid-sealed.json").write_text(json.dumps(sealed))  # the first write happened...
    (rd / "invalid.json").write_text(json.dumps(legacy))  # ...the second did not
    rows = run.invalid(out)
    assert len(rows) == 1 and "arm" not in rows[0] and "brain" not in rows[0]
    _assert_blind(_blind_files(out), fake_fast)
    assert json.loads((rd / "invalid-sealed.json").read_text()) == sealed  # the sealed record is left as it was
