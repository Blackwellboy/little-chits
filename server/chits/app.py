"""HTTP + WebSocket API. Run: uvicorn chits.app:app --port 8000"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import sizing, theme, views
from .brain.llm import BrainConfig, LLMBrain, probe_endpoint, scan_local
from .brain.mind import INSTINCT
from .runtime import SPEEDS, Runtime
from .sim.agent import TICKS_PER_DAY

logging.basicConfig(level=os.environ.get("CHITS_LOG", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")
try:  # also keep a server log next to the data, for checking what happened while nobody watched
    _dd = Path(os.environ.get("CHITS_DATA_DIR", "data"))
    _dd.mkdir(parents=True, exist_ok=True)
    _fh = logging.FileHandler(_dd / "server.log")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(_fh)
except OSError:
    pass
log = logging.getLogger("chits.app")
logging.getLogger("httpx").setLevel(logging.WARNING)

rt: Optional[Runtime] = None


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    global rt
    rt = Runtime()
    await rt.start()
    await rt.autodetect()
    log.info("Little Chits running: %s", ", ".join(f"{w.id}@{w.tick}" for w in rt.worlds.values()))
    hint = None
    if rt.first_run and os.environ.get("CHITS_FIRST_RUN_HINT") == "1":
        # the `little-chits` command's first run: say whether the model found keeps up with the new world
        hint = asyncio.create_task(sizing.first_run_hint(rt, lambda line: print(line, flush=True)))
    try:
        yield
    finally:
        if hint is not None:
            hint.cancel()
        await rt.stop()


app = FastAPI(title="Little Chits", lifespan=lifespan)


def _token_ok(auth: Optional[str], query_token: Optional[str]) -> bool:
    """CHITS_TOKEN (T29/F21): when set, private API reads and all mutations need it."""
    tok = os.environ.get("CHITS_TOKEN", "")
    if not tok:
        return True
    if auth and auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip(), tok):
        return True
    return bool(query_token) and hmac.compare_digest(query_token, tok)


@app.middleware("http")
async def _require_token(request, call_next):
    path, method = request.url.path, request.method
    # Keep only the tiny liveness response public. World state, decisions, diagnostics, replay and god-palette
    # reads are private when a token is configured; the browser already sends its remembered token on API calls.
    public_health = path == "/api/health" and method in ("GET", "HEAD")
    if path.startswith("/api/") and method != "OPTIONS" and not public_health \
            and not _token_ok(request.headers.get("authorization"), request.query_params.get("token")):
        return JSONResponse({"error": "this Little Chits needs its access token (Authorization: Bearer <token>)"},
                            status_code=401)
    return await call_next(request)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def R() -> Runtime:
    assert rt is not None
    return rt


def world(wid: str):
    w = R().worlds.get(wid)
    if not w:
        raise HTTPException(404, f"no world {wid}")
    return w


# ------------------------------------------------------------------ read
@app.get("/api/health")
def health():
    r = R()
    return {"ok": True, "worlds": {w.id: {"tick": w.tick, "population": len(w.agents)} for w in r.worlds.values()},
            "control": r.control_state(), "clients": len(r.clients), "mode": r.mode, "first_run": r.first_run,
            "autodetected": r.autodetected, "theme": theme.active(),
            "brains": {wid: (b or {}).get("label", "Instinct") for wid, b in r.brain_summary().items()}}


@app.get("/api/worlds")
def worlds():
    r = R()
    return [{**views.world_meta(w), "clock": w.clock(), "stats": w.stats(), "brain": r.brain_summary().get(w.id)}
            for w in r.worlds.values()]


@app.get("/api/worlds/{wid}/agents/{aid}")
def agent(wid: str, aid: str):
    w = world(wid)
    a = w.agents.get(aid) or w.dead.get(aid)
    if not a:
        raise HTTPException(404, "no such chit")
    b = R().mind.brains.get(a.brain)
    return views.agent_detail(w, a, b.label if b else "Instinct")


@app.get("/api/worlds/{wid}/agents")
def agents(wid: str, dead: bool = False):
    w = world(wid)
    src = list(w.agents.values()) + (list(w.dead.values()) if dead else [])
    out = []
    for a in src:
        d = views.agent_brief(w, a)
        d.update(alive=a.alive, age=round(a.age(w.tick if a.alive else a.died), 1), generation=a.generation,
                 goal=a.goal, known=len(a.knows), built=a.stats.get("built", 0), cause=a.cause_of_death,
                 role=_role(a), job=a.job, job_source=a.job_source, leader=a.id == w.leader)
        out.append(d)
    return out


def _role(a) -> str:
    """Observer-inferred label from behaviour. Never an assignment."""
    s = a.stats
    scores = {
        "builder": s.get("built", 0) * 2.5 + s.get("repaired", 0) * 2 + s.get("refueled", 0) * 0.5,
        "tinkerer": s.get("experiments", 0) * 0.5 + s.get("crafted", 0) * 0.5 + s.get("learned", 0) * 0.3,
        "farmer": s.get("planted", 0) * 3 + s.get("harvested", 0) * 3,
        "teacher": s.get("taught", 0) * 4 + s.get("wrote", 0) * 4,
        "gatherer": sum(v for k, v in s.items() if k.startswith("gathered_")) * 0.08 + s.get("stored", 0) * 0.05,
        "explorer": s.get("explored", 0) * 3,
        "talker": s.get("said", 0) * 1.5,
        "scholar": s.get("read", 0) * 4,
    }
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0] if best[1] >= 6 else "generalist"


@app.get("/api/worlds/{wid}/structures/{sid}")
def structure(wid: str, sid: str):
    w = world(wid)
    s = w.structures.get(sid)
    if not s:
        raise HTTPException(404, "no such structure")
    v = views.structure_view(s, w)
    everyone = {**w.dead, **w.agents}
    v["builder_names"] = [everyone[b].name for b in s.builders if b in everyone]
    v["blurb"] = views.DESIGNS[s.design].blurb
    v["created_day"] = s.created // 240 + 1
    v["completed_day"] = s.completed // 240 + 1 if s.completed >= 0 else None
    v["shelf"] = [w.tablets[t].text + f" — {w.tablets[t].author_name}" for t in s.shelf if t in w.tablets]
    v["residents"] = [a.name for a in w.agents.values() if a.home == s.id]
    # what the chips are called: an invention's key (inv_b_11) is not its name
    v["item_names"] = {k: w.item_name(k) for k in {*s.produced, *s.storage, *v.get("needs", {})}}
    v["working"] = s.worked_until > w.tick
    v["workers"] = [a.name for a in w.agents.values() if a.plan and a.plan[0].get("do") == "work"
                    and (a.plan[0].get("_s") or {}).get("st") == s.id]
    return v


@app.get("/api/knowledge")
def knowledge():
    return views.knowledge_table(list(R().worlds.values()))


@app.get("/api/inventions")
def inventions():
    """Each world's own inventions (T20): what it is, what it's for, who invented it, how many know it."""
    out = {}
    for w in R().worlds.values():
        out[w.id] = [{**inv, "day": inv["tick"] // 240 + 1,
                      "knowers": sum(1 for a in w.agents.values() if f"recipe:{inv['key']}" in a.knows)}
                     for inv in w.inventions.values()]
    return out


def _replay_data(w, from_tick: int, to_tick: Optional[int], epoch: Optional[str]) -> Dict[str, Any]:
    r = R()
    r._flush_events(w)
    ep = epoch or w.epoch
    evs = [e for e in r.store.events(w.id, since_tick=from_tick, until_tick=to_tick, min_importance=2, limit=20000, epoch=ep)]
    return {"meta": {**views.world_meta(w), "epoch": ep}, "keyframes": r.store.keyframes(w.id, from_tick, to_tick, ep),
            "events": evs}


@app.get("/api/worlds/{wid}/replay")
def replay(wid: str, request: Request, epoch: Optional[str] = None):
    """Keyframes and notable events for scrubbing back through history (T33). One epoch at a time."""
    w = world(wid)
    q = request.query_params
    from_tick = int(q.get("from") or 0)
    to_tick = int(q["to"]) if q.get("to") else None
    return _replay_data(w, from_tick, to_tick, epoch)


@app.get("/api/replay/export")
def replay_export(days: int = 7):
    """A single-file replay bundle anyone can open in web/replay.html (T33): no server, no GPU needed."""
    import base64
    import time as _time

    r = R()
    days = max(1, min(400, days))
    out: Dict[str, Any] = {"version": 1, "exported": _time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": r.mode,
                           "theme": theme.active(), "worlds": {}}
    summary = r.brain_summary()
    for wid, w in r.worlds.items():
        frm = max(0, w.tick - days * 240)
        d = _replay_data(w, frm, None, None)
        if d["keyframes"] and d["keyframes"][0].get("s") is None:
            # start from a day keyframe so the viewer has the buildings from the first frame
            prev = [k for k in r.store.keyframes(w.id, max(0, frm - 240), frm, w.epoch) if k.get("s") is not None]
            if prev:
                d["keyframes"].insert(0, prev[-1])
        amt = bytes(min(255, max(0, int(v))) for v in w.res_amt)
        out["worlds"][wid] = {
            "meta": d["meta"], "brain": summary.get(wid, {}).get("label", "Instinct"),
            "terrain": {"size": w.w, "seed": w.seed, "tiles": base64.b64encode(bytes(w.tiles)).decode(),
                        "res_kind": base64.b64encode(bytes(w.res_kind)).decode(), "res_amt": base64.b64encode(amt).decode()},
            "keyframes": d["keyframes"], "events": d["events"],
            "names": {a.id: a.name for a in list(w.agents.values()) + list(w.dead.values())},
            "hues": {a.id: a.hue for a in list(w.agents.values()) + list(w.dead.values())},
        }
    return JSONResponse(out, headers={"Content-Disposition": f'attachment; filename="little-chits-replay-{_time.strftime("%Y%m%d-%H%M")}.json"'})


@app.get("/api/items")
def items_catalog():
    """Every base item and artifact, for the god palette (T28)."""
    from .sim.artifacts import ARTIFACTS
    from .sim.items import ITEMS

    return [{"key": k, "name": it.name, "icon": it.icon, "artifact": k in ARTIFACTS, "props": list(it.props)}
            for k, it in ITEMS.items()]


class GodBody(BaseModel):
    action: str
    x: Optional[int] = None
    y: Optional[int] = None
    item: Optional[str] = None
    qty: Optional[int] = None


@app.post("/api/worlds/{wid}/god")
def god(wid: str, body: GodBody):
    """God mode (T28): drop anything, or meddle. Marks the run as a sandbox; refused in experiments."""
    world(wid)
    try:
        text = R().god(wid, body.action.strip().lower(), body.x, body.y, (body.item or "").strip() or None, body.qty)
    except PermissionError as e:
        raise HTTPException(409, f"god mode is {e}: an experiment stays untouched")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "event": text}


class SaveBody(BaseModel):
    name: str = ""


@app.post("/api/savepoints")
def savepoint_create(body: SaveBody):
    return R().save_point(body.name)


@app.get("/api/savepoints")
def savepoint_list():
    return R().store.save_points()


@app.post("/api/savepoints/{sid}/restore")
def savepoint_restore(sid: int):
    try:
        ok = R().restore_point(sid)
    except PermissionError as e:
        raise HTTPException(409, f"restoring is {e}: an experiment never rewinds")
    if not ok:
        raise HTTPException(404, "no such save point")
    return {"ok": True}


@app.delete("/api/savepoints/{sid}")
def savepoint_delete(sid: int):
    if not R().store.delete_save_point(sid):
        raise HTTPException(404, "no such save point")
    return {"ok": True}


def _rivals_data() -> Dict[str, Any]:
    r = R()
    ws = list(r.worlds.values())
    table = {}
    for w in ws:
        st = w.stats()
        rels = w.relations
        table[w.id] = {"name": w.name, "population": st["population"], "discoveries": st["discoveries"],
                       "structures": st["structures"], "trades": sum(x.get("trades", 0) for x in rels.values()),
                       "raids": sum(x.get("raids", 0) for x in rels.values()), "gifts": sum(x.get("gifts", 0) for x in rels.values())}
    return {"mode": r.mode, "contact": r.contact, "relations": {w.id: w.relations for w in ws}, "table": table}


@app.get("/api/rivals")
def rivals():
    """Age of Chitpires (T34): how the islands stand with each other, and a side-by-side count."""
    return _rivals_data()


@app.get("/api/rivals/card.svg")
def rivals_card():
    from fastapi.responses import Response
    from .story.card import scoreboard_svg

    r = R()
    d = _rivals_data()
    summary = r.brain_summary()
    worlds = [{"id": w.id, "name": w.name, "brain": summary.get(w.id, {}).get("label", ""), "culture": w.culture,
               "day": w.day + 1, "stats": w.stats()} for w in r.worlds.values()]
    rel = next(iter(d["relations"].values()), {})
    state = next(iter(rel.values()), {}).get("state", "unknown") if rel else "unknown"
    moment = {"world": "", "text": f"The islands are {'at ' + state if state in ('war', 'peace') else state}", "kind": state}
    return Response(scoreboard_svg(worlds, moment, title="AGE OF CHITPIRES"), media_type="image/svg+xml")


@app.get("/api/compare")
def compare_worlds():
    """How differently did the two worlds think (T23)? Needs two worlds."""
    from .story.divergence import compare, to_markdown, to_tweet

    ws = list(R().worlds.values())
    if len(ws) < 2:
        raise HTTPException(400, "comparing needs two worlds (start a model-vs-model or culture game)")
    c = compare(ws[0], ws[1])
    return {"compare": c, "markdown": to_markdown(c), "tweet": to_tweet(c)}


@app.get("/api/government")
def government():
    """Each world's chief or elder and its laws (T26). An authored institution; what happens inside it is real."""
    out = {}
    for w in R().worlds.values():
        lead = w.agents.get(w.leader)
        out[w.id] = {"leader": lead.name if lead else None, "leader_id": w.leader or None,
                     "title": "chief" if w.flags.get("say") else "elder",
                     "since_day": w.leader_since // 240 + 1 if w.leader_since >= 0 else None, "laws": list(reversed(w.laws))}
    return out


@app.get("/api/beliefs")
def beliefs():
    """What each world's chits believe (T21), with followers, shrines and tablets. Beliefs, not facts."""
    return {w.id: views.belief_list(w) for w in R().worlds.values()}


@app.get("/api/worlds/{wid}/events")
def events(wid: str, since: int = 0, min_importance: int = 1, limit: int = 300):
    world(wid)
    r = R()
    r._flush_events(r.worlds[wid])
    return r.store.events(wid, since_tick=since, min_importance=min_importance, limit=limit, epoch=r.worlds[wid].timeline())


@app.get("/api/worlds/{wid}/decisions")
def decisions(wid: str, agent: Optional[str] = None, limit: int = 100):
    """Every model decision: which model, which prompt, how long, parsed how, adopted or stale (F2)."""
    world(wid)
    return R().store.decisions(wid, agent, max(1, min(limit, 5000)))


@app.get("/api/decisions.jsonl")
def decisions_jsonl():
    from fastapi.responses import PlainTextResponse

    rows = R().store.decisions(limit=1_000_000)
    return PlainTextResponse("\n".join(json.dumps(r) for r in reversed(rows)) + "\n")


@app.get("/api/worlds/{wid}/lineage/{knowledge}")
def lineage(wid: str, knowledge: str):
    """How one piece of knowledge travelled: first discovery, every delivery, and who made it work (F7)."""
    w = world(wid)
    first = w.first.get(knowledge)
    chain = [d for d in w.deliveries if d.get("knowledge") == knowledge]
    names = {a.id: a.name for a in list(w.agents.values()) + list(w.dead.values())}
    worked = sorted(({"agent": a.id, "name": a.name, "tick": a.knows[knowledge].get("worked_tick")}
                     for a in list(w.agents.values()) + list(w.dead.values())
                     if knowledge in a.knows and a.knows[knowledge].get("status") == "worked"),
                    key=lambda x: x["tick"] or 0)
    return {"knowledge": knowledge, "first": first,
            "deliveries": [{**d, "from_name": names.get(d["from"]), "to_name": names.get(d["to"])} for d in chain],
            "worked": worked}


@app.get("/api/worlds/{wid}/recap")
def story_so_far(wid: str):
    """📜 The story so far, for someone who has just arrived: a count or a quote on every line."""
    from .story.recap import recap

    w = world(wid)
    rt = R()
    counts = rt.store.count_kinds(w.id, ("law", "storm", "drought"), epoch=w.timeline())
    # (a lookout driving a wolf off is logged as a "wolf" event too: only the attacks)
    counts.update(rt.store.count_kinds(w.id, ("wolf",), epoch=w.timeline(), unless="driven_off"))
    rival = next((o for o in rt.worlds.values() if o is not w), None)
    return recap(w, counts, rival)


@app.get("/api/worlds/{wid}/hall")
def hall_of_ancestors(wid: str, limit: int = 60):
    """🏛 A short biography for every chit that mattered, from its own record, the most recently departed first."""
    return views.hall(world(wid), max(1, min(300, limit)))


@app.get("/api/worlds/{wid}/eras")
def eras(wid: str):
    """The world's age and each age's first maker (views.eras): lamps and statues in the renderer."""
    return views.eras(world(wid))


@app.get("/api/worlds/{wid}/family/{aid}")
def family(wid: str, aid: str):
    """A chit's family tree, living and dead."""
    f = views.family(world(wid), aid)
    if f is None:
        raise HTTPException(404, "no such chit")
    return f


@app.get("/api/worlds/{wid}/spread/{knowledge}")
def spread(wid: str, knowledge: str):
    """How the village came to know a thing: a tree from whoever found it (views.spread)."""
    return views.spread(world(wid), knowledge)


@app.get("/api/worlds/{wid}/progress")
def progress(wid: str):
    """🧭 How far a world has come, what it is doing now, and how its latest achievements happened."""
    w = world(wid)
    since = max(0, (w.tick // TICKS_PER_DAY - 1) * TICKS_PER_DAY)
    evs = R().store.events(w.id, since_tick=since, min_importance=1, limit=5000, epoch=w.timeline())
    return views.progress(w, evs)


@app.get("/api/worlds/{wid}/settlements")
def settlements(wid: str):
    from .sim.settlements import detect

    return [s.to_dict() for s in detect(world(wid))]


@app.get("/api/worlds/{wid}/stories/{day}")
def story(wid: str, day: int):
    world(wid)
    p = R().data_dir / "stories" / wid / f"day-{day:03d}.md"
    if not p.exists():
        raise HTTPException(404, "no story for that day yet")
    return {"markdown": p.read_text()}


class Narrator(BaseModel):
    brain: str = ""


@app.post("/api/narrator")
def set_narrator(body: Narrator):
    r = R()
    if body.brain and body.brain not in r.mind.brains:
        raise HTTPException(404, "no such brain")
    r.mind.narrator = body.brain
    r.mind.save()
    return {"ok": True, "narrator": r.mind.narrator}


@app.get("/api/worlds/{wid}/sagas")
def sagas(wid: str):
    world(wid)
    d = R().data_dir / "stories" / wid
    return [{"week": int(p.stem.split("-")[1])} for p in sorted(d.glob("week-*.md"))] if d.exists() else []


@app.get("/api/worlds/{wid}/sagas/{week}")
def saga(wid: str, week: int):
    world(wid)
    p = R().data_dir / "stories" / wid / f"week-{week:02d}.md"
    if not p.exists():
        raise HTTPException(404, "no saga for that week yet")
    return {"markdown": p.read_text()}


@app.get("/api/story/x")
def story_x(since_day: int = 1, max_posts: int = 6):
    """A ready-to-post thread from real moments in every world."""
    from .story.moments import find_moments
    from .story.xpost import make_thread, pick_clip
    from .sim.agent import TICKS_PER_DAY as TPD

    r = R()
    summary = r.brain_summary()
    worlds, moments = [], {}
    for w in r.worlds.values():
        r._flush_events(w)
        worlds.append({"id": w.id, "name": w.name, "brain": summary.get(w.id, {}).get("label", ""), "culture": w.culture,
                       "day": w.day + 1, "stats": w.stats()})
        evs = r.store.events(w.id, since_tick=max(0, (since_day - 1) * TPD), min_importance=1, limit=50000, epoch=w.timeline())
        moments[w.id] = find_moments(evs, r.names(w))
    return {"posts": make_thread(worlds, moments, max(2, min(max_posts, 12))), "clip": pick_clip(moments)}


def _story_inputs(since_day: int = 1):
    from .story.moments import find_moments
    from .sim.agent import TICKS_PER_DAY as TPD

    r = R()
    summary = r.brain_summary()
    worlds, moments = [], {}
    for w in r.worlds.values():
        r._flush_events(w)
        worlds.append({"id": w.id, "name": w.name, "brain": summary.get(w.id, {}).get("label", ""), "culture": w.culture,
                       "day": w.day + 1, "stats": w.stats()})
        evs = r.store.events(w.id, since_tick=max(0, (since_day - 1) * TPD), min_importance=1, limit=50000, epoch=w.timeline())
        moments[w.id] = find_moments(evs, r.names(w))
    return worlds, moments


@app.get("/api/story/card.svg")
def story_card(since_day: int = 1):
    from fastapi.responses import Response
    from .story.card import scoreboard_svg
    from .story.xpost import pick_clip

    worlds, moments = _story_inputs(since_day)
    return Response(scoreboard_svg(worlds, pick_clip(moments)), media_type="image/svg+xml")


@app.get("/api/story/card.png")
def story_card_png(since_day: int = 1):
    from fastapi.responses import Response
    from .story.card import scoreboard_svg
    from .story.xpost import pick_clip

    try:
        import cairosvg  # optional
    except ImportError:
        return JSONResponse({"error": "PNG needs the optional cairosvg package: pip install cairosvg. The SVG version is at /api/story/card.svg"}, status_code=501)
    worlds, moments = _story_inputs(since_day)
    return Response(cairosvg.svg2png(bytestring=scoreboard_svg(worlds, pick_clip(moments)).encode()), media_type="image/png")


@app.get("/api/run")
def run_manifest():
    """What this run is: contract, mode, seed, exact brains and settings, prompt version, sandbox flags."""
    return R().write_manifest()


@app.get("/api/scorecard")
def scorecard():
    """Which model is building the better civilisation, side by side (diag.scorecard)."""
    from . import diag

    return diag.scorecard(R())


@app.get("/api/diagnostics")
def diagnostics_json():
    """Is the model keeping up, are plans working, is anyone stuck? (see diag.py)"""
    from . import diag

    return diag.report(R())


@app.get("/api/diagnostics.txt")
def diagnostics_txt():
    from fastapi.responses import PlainTextResponse
    from . import diag

    return PlainTextResponse(diag.text(diag.report(R())))


@app.get("/api/worlds/{wid}/log.txt")
def world_log(wid: str, min_importance: int = 1, days: int = 0):
    """Everything that happened, as plain text: one line per event, plus a daily numbers line.
    Handy for checking a long run went smoothly (or pasting into a chat with a model)."""
    from fastapi.responses import PlainTextResponse

    w = world(wid)
    r = R()
    r._flush_events(w)
    since = max(0, w.tick - days * TICKS_PER_DAY) if days else 0
    evs = r.store.events(wid, since_tick=since, min_importance=min_importance, limit=200000, epoch=w.timeline())
    brain = r.mind.world_brain.get(wid, INSTINCT)
    lines = [f"# {w.name} ({w.label}) · seed {w.seed} · brain {brain} · day {w.day}", ""]
    hist = {h.get("day"): h for h in w.history}
    day = None
    for e in evs:
        d = e["tick"] // TICKS_PER_DAY + 1
        if d != day:
            day = d
            h = hist.get(d - 1) or {}
            nums = f"  pop {h.get('population')} · discoveries {h.get('discoveries')} · structures {h.get('structures')}" if h else ""
            lines.append(f"\n== Day {d}{nums}")
        hh = (e["tick"] % TICKS_PER_DAY) * 24 // TICKS_PER_DAY
        lines.append(f"{hh:02d}h  {e['kind']:<10} {e['text']}")
    return PlainTextResponse("\n".join(lines) + "\n")


@app.get("/api/worlds/{wid}/chronicle")
def chronicle(wid: str):
    w = world(wid)
    r = R()
    r._flush_events(w)
    evs = r.store.events(wid, min_importance=1, limit=20000, epoch=w.timeline())
    days = sorted({e["tick"] // 240 + 1 for e in evs}, reverse=True)
    return [views.day_chronicle(w, evs, d) for d in days[:60]]


@app.get("/api/worlds/{wid}/history")
def history(wid: str):
    return world(wid).history


# ------------------------------------------------------------------ control
class Control(BaseModel):
    speed: Optional[int] = None
    paused: Optional[bool] = None
    pace_to_brain: Optional[bool] = None


class ThemeBody(BaseModel):
    theme: str


@app.get("/api/theme")
def get_theme():
    return {"theme": theme.active(), "themes": list(theme.THEMES)}


@app.post("/api/theme")
def set_theme(b: ThemeBody):
    """The Look button: switch the theme in the game. Presentation only (the same random numbers either way); every
    observer redraws, and chits born from now on get the theme's names."""
    r = R()
    if r.contract == "experiment":  # (newborns' names reach the models' prompts: an experiment stays untouched)
        raise HTTPException(409, "the look can't be switched during an experiment run")
    try:
        t = theme.choose(b.theme, r.data_dir)
    except ValueError as e:
        raise HTTPException(400, str(e))
    r._broadcast_snapshots()  # (the hello carries the theme: each observer reloads into it)
    return {"ok": True, "theme": t}


@app.post("/api/experiment/end")
def end_experiment():
    """🧪 → play: end an experiment run and keep playing the same worlds (issue #64)."""
    r = R()
    if r.contract != "experiment":
        raise HTTPException(409, "this game isn't an experiment run")
    r.end_experiment()
    return r.control_state()


@app.post("/api/control")
def control(c: Control):
    r = R()
    wants_resume = (c.speed is not None and c.speed != 0) or c.paused is False
    if wants_resume and (r.save_errors or r.invalid_reason):
        why = r.invalid_reason or "; ".join(f"{w}: {e}" for w, e in r.save_errors.items())
        raise HTTPException(409, f"cannot resume while durability is unresolved: {why}")
    if c.speed is not None:
        if c.speed not in SPEEDS:
            raise HTTPException(400, f"speed must be one of {list(SPEEDS)}")
        r.speed = c.speed
        r.paused = c.speed == 0
    if c.paused is not None:
        r.paused = c.paused
    if c.pace_to_brain is not None:
        if r.contract == "experiment" and not c.pace_to_brain:
            raise HTTPException(409, "an experiment run always waits for its models")
        r.pace_to_brain = c.pace_to_brain
    return r.control_state()


class Reset(BaseModel):
    seed: Optional[int] = None
    chits: Optional[int] = None
    size: Optional[int] = None
    mode: Optional[str] = None  # "versus" (same island, one model each), "single" (one world), "culture"
    brains: Optional[Dict[str, str]] = None  # world id -> brain id for the new match
    contract: Optional[str] = None  # "play" (resilient, default) or "experiment" (strict, see F1)
    contact: Optional[bool] = None  # boats between the islands (never in experiments)


@app.post("/api/reset")
def reset(body: Reset):
    r = R()
    if body.chits is not None and not 2 <= body.chits <= 60:
        raise HTTPException(400, "chits must be 2..60")
    if body.size is not None and not 64 <= body.size <= 512:
        raise HTTPException(400, "size must be 64..512")
    from .runtime import MODES

    if body.mode is not None and body.mode not in MODES:
        raise HTTPException(400, f"mode must be one of {', '.join(MODES)}")
    from .runtime import CONTRACTS

    if body.contract is not None and body.contract not in CONTRACTS:
        raise HTTPException(400, f"contract must be one of {', '.join(CONTRACTS)}")
    try:
        r.reset(body.seed, body.chits, body.size, body.mode, body.brains, body.contract, body.contact)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "worlds": [views.world_meta(w) for w in r.worlds.values()]}


@app.post("/api/save")
def save():
    R().save_all()
    return {"ok": True}


# ------------------------------------------------------------------ brains
@app.get("/api/brains")
def brains():
    from . import diag

    r = R()
    out = r.mind.status(speed=diag.brain_ratings(r))
    for row in out["brains"]:  # "Keeps up with about N chits", from its live replies or a probe (sizing.py)
        row["capacity"] = sizing.capacity(r.mind.brains[row["config"]["id"]])
    return out


@app.post("/api/brains/{bid}/capacity")
async def brain_capacity(bid: str):
    """How many chits this brain keeps up with. With no measurement yet, a short probe measures it now."""
    b = R().mind.brains.get(bid)
    if not b:
        raise HTTPException(404, "no such brain")
    return await sizing.measure(b)


class Sizing(BaseModel):
    brains: Dict[str, str] = {}  # world id -> brain id, as a new game would be set up
    measure: bool = False  # probe the brains that have no measurement yet


@app.post("/api/sizing")
async def new_game_size(body: Sizing):
    """Chits per world that the chosen brains keep up with, for the New game dialog. Advice: nothing is changed."""
    mind = R().mind
    if body.measure:
        for bid in sizing.recommend(mind, body.brains)["unmeasured"]:
            await sizing.measure(mind.brains[bid])
    return sizing.recommend(mind, body.brains)


class BrainBody(BaseModel):
    id: Optional[str] = None
    label: Optional[str] = None
    base_url: str
    model: Optional[str] = ""
    api_key: Optional[str] = ""
    max_concurrency: Optional[int] = 6
    timeout: Optional[float] = 90
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 600
    json_mode: Optional[bool] = None  # (a new brain that names neither starts plain, and its first Test finds
    disable_thinking: Optional[bool] = None  # what its server takes: brain/checkup.py)
    enabled: Optional[bool] = True
    prompt_style: Optional[str] = "full"
    escalate_below: Optional[float] = 0.5
    escalate_share: Optional[float] = 0.3
    focus: Optional[bool] = True


def _in_experiment(bid: str) -> bool:
    r = R()
    return r.contract == "experiment" and bid in r.mind.world_brain.values()


def _locked_brain(bid: str) -> None:
    """In an experiment, the brains the worlds use are frozen for the whole run."""
    if _in_experiment(bid):
        raise HTTPException(409, "this brain is in use by an experiment run and can't be changed")


@app.post("/api/brains")
def upsert_brain(b: BrainBody):
    # updating a brain changes only what was sent: filled in with the body's defaults, a request that set the model
    # and slots also reset the live World B brain's prompt_style from "cascade" to "full"
    # (the id first: a body with no id but a label naming an existing brain was filled in with defaults, Codex #42)
    bid = b.id
    if not bid:
        base = (b.label or b.model or "brain").lower()
        bid = "".join(ch if ch.isalnum() else "-" for ch in base).strip("-")[:24] or "brain"
    existing = bid in R().mind.brains
    data = {k: v for k, v in b.model_dump(exclude_unset=existing).items() if v is not None}
    data["id"] = bid
    if not existing:
        # JSON mode on by default produced no decisions at all on servers that refuse it (issue #61): a new brain
        # starts with the request every OpenAI-compatible server takes, and its first Test detects the rest
        data["detect"] = b.json_mode is None and b.disable_thinking is None
        data.setdefault("json_mode", False)
        data.setdefault("disable_thinking", False)
    elif "json_mode" in data or "disable_thinking" in data:
        data["detect"] = False  # (set by hand: a Test no longer chooses them)
    _locked_brain(data["id"])
    br = R().mind.upsert(data)
    return {"ok": True, "brain": br.cfg.public()}


@app.delete("/api/brains/{bid}")
def delete_brain(bid: str):
    _locked_brain(bid)
    r = R()
    r.mind.remove(bid)
    for w in r.worlds.values():
        for a in w.agents.values():
            if a.brain == bid:
                a.brain = INSTINCT
    return {"ok": True}


@app.post("/api/brains/{bid}/test")
async def test_brain(bid: str):
    """One real, tiny decision, and for whatever went wrong a plain cause and a fix (brain/checkup.py). A brain
    added without settings gets the ones its server takes, unless an experiment is using it."""
    from .brain import checkup

    r = R()
    b = r.mind.brains.get(bid)
    if not b:
        raise HTTPException(404, "no such brain")
    out = await checkup.test_brain(r.mind, b, locked=_in_experiment(bid))
    if out["reply"] is not None:  # it answered: as before, a Test is how a brain is found to be back
        b.stats.consecutive_fail, b.stats.last_ok = 0, time.time()
    return out


class Probe(BaseModel):
    base_url: str
    api_key: Optional[str] = ""


@app.post("/api/brains/probe")
async def probe(p: Probe):
    """List models on an endpoint before saving it. Tries with and without /v1."""
    return await probe_endpoint(p.base_url, p.api_key or "")


@app.get("/api/brains/scan")
async def scan(host: str = "127.0.0.1"):
    """Find model servers on the usual local ports (5090/3090 presets, llama.cpp, Ollama, LM Studio...)."""
    found = await scan_local(host)
    known = {b.cfg.base_url.rstrip("/") for b in R().mind.brains.values() if hasattr(b, "cfg")}
    for f in found:
        f["added"] = f["base_url"].rstrip("/") in known
    return {"host": host, "found": found}


class ForkReq(BaseModel):
    brain: str = "instinct"
    culture: Optional[str] = None


@app.post("/api/worlds/{wid}/fork")
def make_fork(wid: str, body: ForkReq):
    """🔀 What if: a copy of this world as it is now, stepping alongside it with another mind or culture."""
    world(wid)
    try:
        return R().fork(wid, body.brain, body.culture)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/forks")
def list_forks():
    return [R().fork_view(fid) for fid in list(R().forks)]


@app.delete("/api/forks/{fid}")
def end_fork(fid: str):
    if not R().end_fork(fid):
        raise HTTPException(404, "no such what-if")
    return {"ok": True}


class Assign(BaseModel):
    brain: str
    agents: Optional[List[str]] = None


@app.post("/api/worlds/{wid}/brain")
def assign(wid: str, body: Assign):
    w = world(wid)
    if R().contract == "experiment":
        raise HTTPException(409, "brains can't be swapped during an experiment run")
    try:
        R().mind.assign(w, body.brain, body.agents)
    except KeyError:
        raise HTTPException(404, "no such brain")
    return {"ok": True, "assign": R().mind.world_brain}


# ------------------------------------------------------------------ live stream
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    if not _token_ok(ws.headers.get("authorization"), ws.query_params.get("token")):
        await ws.close(code=4401)
        return
    await ws.accept()
    r = R()
    q = r.new_client_queue()
    r.enqueue_hello(q)
    r.clients[ws] = q

    async def writer():
        while True:
            msg = await q.get()
            await ws.send_text(msg)

    async def reader():
        while True:
            txt = await ws.receive_text()
            try:
                m = json.loads(txt)
            except ValueError:
                continue
            if m.get("type") == "ping":
                r.push(q, {"type": "pong", "t": m.get("t")})
            elif m.get("type") == "resync":
                r.enqueue_hello(q, resync=True)

    tasks = [asyncio.create_task(writer()), asyncio.create_task(reader())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        r.clients.pop(ws, None)
        for t in tasks:
            t.cancel()


# ------------------------------------------------------------------ auto-record (🎞)
class RecorderBody(BaseModel):
    enabled: Optional[bool] = None
    interval_ms: Optional[int] = None
    fps: Optional[int] = None
    aspect: Optional[str] = None
    moments: Optional[bool] = None
    day_seconds: Optional[int] = None
    retention_gb: Optional[float] = None


@app.get("/api/recorder")
def recorder_status():
    return R().recorder.status()


@app.post("/api/recorder")
def recorder_configure(b: RecorderBody, request: Request):
    # the recorder films this server the way this browser reached it (only the host and port are used)
    url = f"http://127.0.0.1:{request.url.port or 80}"
    return R().recorder.configure(url=url, **b.model_dump())


@app.get("/api/recordings")
def recordings():
    return R().recorder.listing()


@app.post("/api/recordings/{run}/cut/{week}")
def director_cut(run: str, week: int):
    """🎬 A week's best moments, numbered in story order with captions, joined into one live-speed video."""
    return R().recorder.director_cut(run, week)


@app.get("/recordings/{run}/{name}")
def recording_file(run: str, name: str):
    f = R().recorder.file(run, name)
    if f is None:
        raise HTTPException(404, "no such recording")
    media = {".mp4": "video/mp4", ".md": "text/markdown; charset=utf-8", ".json": "application/json"}[f.suffix]
    return FileResponse(f, media_type=media)


# ------------------------------------------------------------------ web app
DIST =Path(os.environ.get("CHITS_WEB_DIST", Path(__file__).resolve().parents[2] / "web" / "dist"))
NOT_PAGES = ("api/", "v1/", "props", "health", "metrics", "slots", "completion", "models", "tokenize")


def page(dist: Path, path: str):
    """A file of the built viewer, its page for any other path, or a JSON 404 for what only an API would serve: a
    model-server probe (GET /v1/models, /props) got the page with a 200 and took the game for a model server, and HEAD
    got 405s by the thousand (audit F22)."""
    f = dist / path
    if path and f.is_file():
        return FileResponse(f)
    if path.startswith(NOT_PAGES):
        return JSONResponse({"error": f"not found: /{path} (this is Little Chits, not a model server)"}, 404)
    return FileResponse(dist / "index.html")


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    def spa(path: str):
        return page(DIST, path)
