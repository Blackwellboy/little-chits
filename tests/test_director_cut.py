"""The director's cut: a week's best filmed moments, numbered in story order with captions, joined into one video."""

import json
import shutil
import subprocess

import pytest

from chits.recorder import CUT_PER_KIND, cut_markdown, cut_plan


def _m(name, day, kind, importance, tick, caption=""):
    return {"name": name, "clip": f"{name}.mp4", "day": day, "kind": kind, "importance": importance, "tick": tick,
            "world": "A", "world_name": "Firstlight", "clock": "08:00", "caption": caption or name, "seconds": 15.0}


def test_the_cut_takes_the_best_of_the_week_and_tells_them_in_order():
    ms = [_m(f"el{i}", 2, "election", 4, 100 + i) for i in range(5)]  # five elections...
    ms += [_m("disc", 3, "discovery", 5, 900), _m("first", 4, "first", 4, 50), _m("note", 5, "note", 1, 60)]
    ms += [_m("next_week", 9, "discovery", 5, 3000)]
    plan = cut_plan(ms, week=1, n=6)  # (without the cap, a 4th election would beat the note)
    kinds = [c["kind"] for c in plan]
    assert kinds.count("election") == CUT_PER_KIND and "discovery" in kinds and "first" in kinds
    assert "next_week" not in {c["clip"][:-4] for c in plan}
    assert [c["n"] for c in plan] == [1, 2, 3, 4, 5, 6]
    assert plan[0]["clip"] == "first.mp4" and plan[-1]["clip"] == "disc.mp4"  # in the order they happened
    assert plan[0]["file"] == "cut-01-01-first.mp4"
    md = cut_markdown(1, plan, "cut-01.mp4")
    assert "[▶ Watch the whole cut](cut-01.mp4)" in md and "01. **Day 4, 08:00, Firstlight**: first" in md


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_a_directors_cut_is_made_from_the_filmed_moments(tmp_path):
    from chits.runtime import Runtime

    rt = Runtime(tmp_path)
    rt.reset(seed=5, chits=6, size=64, mode="versus")
    rec = rt.recorder
    d = rec.run_dir()
    d.mkdir(parents=True)
    for i, (kind, imp) in enumerate((("discovery", 5), ("election", 4), ("first", 4))):
        m = _m(f"moment-00{i + 1}-A-{kind}-1", i + 1, kind, imp, 100 * (i + 1), f"something {kind}")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=1", "-r", "10",
                        "-pix_fmt", "yuv420p", str(d / m["clip"])], check=True)
        (d / f"{m['name']}.json").write_text(json.dumps(m))
    out = rec.director_cut(rt.run_id, 1)
    assert out["error"] is None and out["video"] == "cut-01.mp4" and len(out["clips"]) == 3
    assert (d / "cut-01.mp4").stat().st_size > 0 and (d / "cut-01-01-moment-001-A-discovery-1.mp4").exists()
    assert "something election" in (d / "cut-01.md").read_text()
    listed = rec.listing()[0]["cuts"]
    assert listed == [{"week": 1, "story": "cut-01.md", "video": "cut-01.mp4"}]
    assert rec.director_cut(rt.run_id, 5)["clips"] == [] and rec.director_cut("../x", 1)["error"]
    (d / "moment-003-A-first-1.json").unlink()  # a moment gone: the remake has two clips, and only two
    assert len(rec.director_cut(rt.run_id, 1)["clips"]) == 2
    assert sorted(p.name[:9] for p in d.glob("cut-01-*.mp4")) == ["cut-01-01", "cut-01-02"]
    rt.store.db.close()
    import asyncio

    asyncio.run(rt.mind.close())
