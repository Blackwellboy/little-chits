"""A 1200×675 scoreboard card for X posts: model vs model, their numbers, and the moment of the day."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

COLOR = {"direct": "#ffb86b", "stigmergy": "#7dd3fc"}
FONT = "Silkscreen, 'Press Start 2P', monospace"


def _e(s: Any) -> str:
    return escape(str(s), {'"': "&quot;"})


def _wrap(text: str, width: int = 70, lines: int = 2) -> List[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= width:
            cur = f"{cur} {w}" if cur else w
        else:
            out.append(cur)
            cur = w
            if len(out) == lines:
                break
    if cur and len(out) < lines:
        out.append(cur)
    if " ".join(out) != " ".join(words):
        last = out[-1] if out else ""
        out[-1:] = [(last[: width - 1].rstrip() + "…")]
    return out


def _chit(x: float, y: float, r: float, color: str) -> str:
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>'
            f'<rect x="{x - r * 0.45}" y="{y - r * 0.25}" width="{r * 0.22}" height="{r * 0.3}" fill="#1b2336"/>'
            f'<rect x="{x + r * 0.23}" y="{y - r * 0.25}" width="{r * 0.22}" height="{r * 0.3}" fill="#1b2336"/>')


def scoreboard_svg(worlds: List[Dict[str, Any]], moment: Optional[Dict[str, Any]] = None, title: str = "LITTLE CHITS") -> str:
    W, H = 1200, 675
    day = max((w.get("day", 1) for w in worlds), default=1)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="#1c2540"/><stop offset="1" stop-color="#0d1220"/></linearGradient></defs>',
             f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
             f'<text x="60" y="80" font-family="{FONT}" font-size="40" fill="#f4efe6">{_e(title)}</text>',
             f'<text x="{W - 60}" y="80" text-anchor="end" font-family="{FONT}" font-size="34" fill="#c9c2b6">Day {day}</text>']
    n = max(1, len(worlds))
    colw = (W - 120) / n
    for i, w in enumerate(worlds[:2]):
        x0 = 60 + i * colw
        cx = x0 + colw / 2
        same = len({x.get("culture", "direct") for x in worlds}) == 1 and len(worlds) > 1
        col = ("#ffb86b", "#7dd3fc")[i] if same else COLOR.get(w.get("culture", "direct"), "#ffb86b")
        st = w.get("stats") or {}
        talk = "can talk" if w.get("culture", "direct") == "direct" else "silent"
        parts.append(f'<rect x="{x0 + 10}" y="120" width="{colw - 20}" height="370" rx="18" fill="#ffffff" fill-opacity="0.04" stroke="{col}" stroke-opacity="0.5"/>')
        parts.append(f'<text x="{cx}" y="180" text-anchor="middle" font-family="{FONT}" font-size="34" fill="{col}">{_e(w.get("brain") or "Instinct")}</text>')
        parts.append(f'<text x="{cx}" y="218" text-anchor="middle" font-family="sans-serif" font-size="22" fill="#c9c2b6">{_e(w.get("name", ""))} · {_e(talk)}</text>')
        for j, (label, key) in enumerate((("chits", "population"), ("discoveries", "discoveries"), ("buildings", "structures"))):
            nx = x0 + colw * (j + 0.5) / 3
            parts.append(f'<text x="{nx}" y="330" text-anchor="middle" font-family="{FONT}" font-size="64" fill="#f4efe6">{_e(st.get(key, 0))}</text>')
            parts.append(f'<text x="{nx}" y="370" text-anchor="middle" font-family="sans-serif" font-size="20" fill="#9aa3b5">{_e(label)}</text>')
        for k in range(3):
            parts.append(_chit(x0 + 60 + k * 46, 450, 16, col))
    if moment and moment.get("text"):
        lines = _wrap(str(moment["text"]))
        parts.append(f'<rect x="60" y="520" width="{W - 120}" height="110" rx="16" fill="#000000" fill-opacity="0.25"/>')
        for k, line in enumerate(lines):
            txt = ("✨ " if k == 0 else "   ") + line
            parts.append(f'<text x="90" y="{565 + k * 38}" font-family="sans-serif" font-size="28" fill="#f4efe6">{_e(txt)}</text>')
    parts.append("</svg>")
    return "".join(parts)
