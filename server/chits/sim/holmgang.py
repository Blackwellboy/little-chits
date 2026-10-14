"""Rune, Sail, Axe: the holmgang, the island folk's duel. Nobody is hurt, and a raid is settled this way too.

It is rock, paper, scissors with a longship's worth of story:

- **rune** binds the **axe** (the spell stays the swinging arm);
- **axe** cuts the **sail**;
- **sail** outruns the **rune** (the wind carries the spell away).

Best of three: the first to win two rounds wins. A tie is thrown again, up to MAX_ROUNDS throws in all; if it is still
undecided then, the one challenged holds its ground.

A chit that names its throws ({"throws": ["rune", "axe", "sail"]}) plays them in turn, round after round. One that
doesn't plays its habit: it keeps a throw that won and changes one that lost (most of the time). Every chit's throws
are tallied in its stats, so a sharp opponent can learn that Bjorn opens with axe, and play rune.

Two pieces of magic bend fate a little:

- a **rune charm** carried into the holmgang turns one lost round: the charm flares, crumbles, and the round is thrown
  again (once, and the charm is spent);
- a **runestone** on a chit's own island within RUNESTONE_WARD tiles wards it: a tied round goes to the warded side
  (when both are warded, ties are thrown again as usual).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .agent import Agent

THROWS = ("rune", "sail", "axe")
BEATS = {"rune": "axe", "axe": "sail", "sail": "rune"}  # each beats the one it names
WHY = {"rune": "the rune binds the axe", "axe": "the axe cuts the sail", "sail": "the sail outruns the rune"}
ICON = {"rune": "ᚱ", "sail": "⛵", "axe": "🪓"}
WINS_NEEDED, MAX_ROUNDS = 2, 9
RUNESTONE_WARD = 12
HABIT_KEEP = 0.7  # how often a chit without named throws follows its habit (win-stay, lose-shift)
PRIDE = 8.0  # the mood a loser loses, and half of it the winner gains: nothing worse


def norm_throw(raw: Any) -> Optional[str]:
    s = str(raw or "").strip().lower()
    aliases = {"rock": "axe", "scissors": "axe", "paper": "sail", "r": "rune", "s": "sail", "a": "axe",
               "runes": "rune", "spell": "rune", "magic": "rune", "sails": "sail", "wind": "sail", "axes": "axe"}
    s = aliases.get(s, s)
    return s if s in THROWS else None


def norm_throws(raw: Any) -> List[str]:
    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()
    if not isinstance(raw, (list, tuple)):
        return []
    return [t for t in (norm_throw(x) for x in list(raw)[:MAX_ROUNDS]) if t]


def habit(a: Agent) -> str:
    """What this chit tends to throw, by its tally (for the scene: '' until it has played)."""
    n = {t: a.stats.get(f"throw_{t}", 0) for t in THROWS}
    total = sum(n.values())
    if not total:
        return ""
    top = max(THROWS, key=lambda t: (n[t], -THROWS.index(t)))
    return f"{top} {n[top]} of {total}"


def seen_habit(a: Agent, o: Agent) -> str:
    """What o threw in the holmgangs a played against it, as a remembers them ('' if none): only what it saw."""
    head = f"In the holmgang {o.name} threw "
    n = {t: 0 for t in THROWS}
    for m in a.memories:
        if m.kind == "holmgang" and m.text.startswith(head):
            for t in m.text[len(head):].split(";")[0].split(", "):
                if t in n:
                    n[t] += 1
    total = sum(n.values())
    if not total:
        return ""
    top = max(THROWS, key=lambda t: (n[t], -THROWS.index(t)))
    return f"{top} {n[top]} times of {total}"


def _habit_throw(a: Agent, rng) -> str:
    last = a.stats.get("holm_last", 0)
    if not last or rng.random() >= HABIT_KEEP:
        return rng.choice(THROWS)
    prev = THROWS[last - 1]
    if a.stats.get("holm_last_won", 0):
        return prev  # it won: throw it again
    return next(t for t in THROWS if BEATS[t] == prev) if rng.random() < 0.5 else BEATS[prev]  # it lost: change


def warded(world, a: Agent) -> bool:
    from . import buildings as BLD

    if a.origin:
        return False  # a stranger's runes stand at home, over the sea
    return any(r.dist(a.x, a.y) <= RUNESTONE_WARD and world.same_land(a, r) for r in BLD.fx(world)["runestone"])


def play(world, a: Agent, b: Agent, a_throws: Sequence[str] = (), b_throws: Sequence[str] = ()) -> Dict[str, Any]:
    """A holmgang between a (the challenger) and b. Returns who won and every throw. Spends rune charms, tallies
    throws, and leaves the moods and memories; the caller decides the stakes."""
    rng = world.rng_for("holmgang")
    named = {a.id: list(a_throws), b.id: list(b_throws)}
    charm = {x.id: x.inventory.get("rune_charm", 0) > 0 for x in (a, b)}
    ward = {a.id: warded(world, a), b.id: warded(world, b)}
    score = {a.id: 0, b.id: 0}
    rounds: List[Dict[str, Any]] = []
    i = 0
    while max(score.values()) < WINS_NEEDED and len(rounds) < MAX_ROUNDS:
        ta, tb = (named[x.id][i % len(named[x.id])] if named[x.id] else _habit_throw(x, rng) for x in (a, b))
        i += 1
        if ta == tb:
            winner = a if ward[a.id] and not ward[b.id] else b if ward[b.id] and not ward[a.id] else None
            rounds.append({"a": ta, "b": tb, "win": winner.id if winner else "", "ward": bool(winner)})
            if winner:
                score[winner.id] += 1
            continue
        winner, loser = (a, b) if BEATS[ta] == tb else (b, a)
        if charm[loser.id]:  # the charm flares: this round never happened
            charm[loser.id] = False
            loser.inventory["rune_charm"] -= 1
            if loser.inventory["rune_charm"] <= 0:
                loser.inventory.pop("rune_charm", None)
            rounds.append({"a": ta, "b": tb, "win": "", "charm": loser.id})
            continue
        score[winner.id] += 1
        rounds.append({"a": ta, "b": tb, "win": winner.id})
    win = a if score[a.id] >= WINS_NEEDED else b  # (undecided after MAX_ROUNDS: the one challenged holds its ground)
    lose = b if win is a else a
    for x, key in ((a, "a"), (b, "b")):
        thrown = [r[key] for r in rounds]
        for t in thrown:
            x.bump(f"throw_{t}")
        x.stats["holm_last"] = THROWS.index(thrown[-1]) + 1
        x.stats["holm_last_won"] = int(x is win)
        x.bump("holm_won" if x is win else "holm_lost")
    lose.mood = max(0.0, lose.mood - PRIDE)
    win.mood = min(100.0, win.mood + PRIDE / 2)
    for x, y, theirs in ((a, b, "b"), (b, a, "a")):
        seen = ", ".join(r[theirs] for r in rounds)
        x.remember(world.tick, f"In the holmgang {y.name} threw {seen}; " + ("I won" if x is win else "I lost"), 4,
                   "holmgang")
    return {"winner": win, "loser": lose, "rounds": rounds, "score": dict(score)}


def tale(res: Dict[str, Any], a: Agent, b: Agent) -> str:
    """The deciding round, told: 'Astrid's rune bound Bjorn's axe'."""
    win = res["winner"]
    last = next((r for r in reversed(res["rounds"]) if r["win"] == win.id), None)
    if last is None:
        return f"{win.name} held their ground"
    if last.get("ward"):
        return f"the runestone's ward turned the tie for {win.name}"
    mine = last["a"] if win is a else last["b"]
    return WHY[mine].replace("the ", f"{win.name}'s ", 1)
