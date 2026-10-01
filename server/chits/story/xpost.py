"""The day's story as a ready-to-post X thread, built only from moments that really happened.

    python -m chits.story.xpost [--url http://127.0.0.1:8000] [--since-day N]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

EMOJI = {"first": "✨", "teaching_chain": "📚", "legacy": "📜", "built_together": "🏗️", "lost_pioneer": "🕯️",
         "birth": "🍼", "storm": "⛈️", "settlement": "🏘️", "ambition": "🌟", "invention": "💡", "belief": "🕯", "scripture": "📜", "era": "🏛️", "launch": "🚀", "money": "🪙", "election": "🗳️", "elder": "👑", "law": "📜", "militia": "🛡️", "theft": "🫳", "fight": "💢", "miracle": "🪄", "revelation": "👽", "voyage": "⛵", "arrival": "🏝️", "contact": "🤝", "war": "⚔️", "peace": "🕊️", "raid": "🏴‍☠️"}
LIMIT = 280


def _d(m: Any) -> Dict[str, Any]:
    if is_dataclass(m):
        return asdict(m)
    return dict(m)


def _cut(s: str, n: int = LIMIT) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _talk(w: Dict[str, Any]) -> str:
    return "they can talk" if w.get("culture", "direct") == "direct" else "they can't"


def _ranked(worlds: List[dict], moments: Dict[str, list]) -> List[tuple]:
    order = {w["id"]: i for i, w in enumerate(worlds)}
    items = []
    for wid, ms in moments.items():
        for rank, m in enumerate(ms):
            items.append((wid, _d(m), rank))
    # best score first; on ties alternate worlds by taking each world's rank-th moment in world order
    items.sort(key=lambda t: (-t[1]["score"], t[2], order.get(t[0], 99), t[1]["tick"]))
    return items


def make_thread(worlds: List[dict], moments: Dict[str, list], max_posts: int = 6) -> List[str]:
    if not worlds:
        return []
    by = {w["id"]: w for w in worlds}
    day = max(w.get("day", 1) for w in worlds)
    ranked = _ranked(worlds, moments)
    if len(worlds) >= 2:
        a, b = worlds[0], worlds[1]
        hook = (f"Day {day} on a tiny island. Two AI civilisations, same start. 🧠 {a.get('brain') or 'Instinct'} runs "
                f"World {a['id']} ({_talk(a)}) vs 🧠 {b.get('brain') or 'Instinct'} runs World {b['id']} ({_talk(b)}). 🧵")
    else:
        a = worlds[0]
        hook = f"Day {day} on a tiny island. One AI civilisation, grown from nothing by 🧠 {a.get('brain') or 'Instinct'}. 🧵"
    used = None
    if ranked:
        used = ranked[0]
        hook = hook + "\n\n" + used[1]["text"]
    posts = [_cut(hook)]
    for wid, m, _ in ranked:
        if len(posts) >= max_posts - 1:
            break
        if used is not None and m is used[1]:
            continue
        brain = by.get(wid, {}).get("brain") or "Instinct"
        posts.append(_cut(f"{EMOJI.get(m['kind'], '•')} World {wid} · {brain}: {m['text']}"))
    bits = []
    for w in worlds:
        st = w.get("stats") or {}
        bits.append(f"World {w['id']} — {st.get('population', 0)} chits, {st.get('discoveries', 0)} discoveries, "
                    f"{st.get('structures', 0)} buildings")
    posts.append(_cut(f"Scoreboard, day {day}: " + " · ".join(bits) + " #LittleChits #AI"))
    return posts[:max(2, max_posts)]


def pick_clip(moments: Dict[str, list]) -> Optional[Dict[str, Any]]:
    best = None
    for wid, ms in moments.items():
        for m in ms:
            m = _d(m)
            if best is None or m["score"] > best[1]["score"]:
                best = (wid, m)
    if not best:
        return None
    wid, m = best
    return {"world": wid, "x": m.get("x"), "y": m.get("y"), "tick": m["tick"], "kind": m["kind"], "text": m["text"]}


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Print today's X thread from a running Little Chits server.")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--since-day", type=int, default=1)
    ap.add_argument("--max-posts", type=int, default=6)
    a = ap.parse_args(argv)
    with urllib.request.urlopen(f"{a.url}/api/story/x?since_day={a.since_day}&max_posts={a.max_posts}") as r:
        d = json.loads(r.read())
    print("\n---\n".join(d["posts"]))


if __name__ == "__main__":
    main()
