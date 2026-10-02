"""One-token elections and trades (docs/UPGRADE_PLAN.md, "cheap scoring elsewhere"; F28).

Where chits think with a model, two everyday choices are put to their own minds as a single letter, the way the
chief chooses the village's next project:

- **An election.** A poll opens with the village's front-runners. Each model-minded adult backs one of them with a
  letter. A voter whose mind doesn't answer before the poll closes votes as the simulator would (for everyone it
  likes), so no answer never means no vote. Worlds without model minds elect at once, exactly as before.
- **A trade.** When a trader makes an offer to a model-minded chit, that chit's mind accepts or refuses it. With no
  answer in time (or no mind available), the chit judges the deal by value as before.

The world keeps the questions and checks every answer; the Mind only asks and reports (brain/mind.py). Shared state
lives in world.civic ("poll", "offers") so it saves with the world.
"""
from __future__ import annotations

import zlib
from typing import Any, Dict, List, Optional

from .agent import TICKS_PER_DAY, Agent

POLL_N = 4  # candidates on a ballot
POLL_TICKS = TICKS_PER_DAY // 4  # a poll closes after this long, answered or not
OFFER_TICKS = 40  # a trader waits this long for a model-minded partner's answer before it judges by value
OFFER_KEEP = 4 * OFFER_TICKS  # an offer nobody collected is dropped after this long


def model_minded(a: Agent) -> bool:
    return getattr(a, "brain", "instinct") != "instinct"


def _civic(world) -> Dict[str, Any]:
    if not hasattr(world, "civic"):
        from . import projects

        projects.init(world)
    return world.civic


# ---------------------------------------------------------------------------------------------- elections
def poll(world) -> Optional[Dict[str, Any]]:
    return _civic(world).get("poll")


def open_poll(world, reason: str, approvals: Dict[str, List[str]], voters: List[Agent]) -> bool:
    """Put the election to the model-minded adults. `approvals`: who each adult backs by the simulator's rule
    (every adult it likes). Returns False (elect at once) when no voter has a model mind or nobody is backed."""
    counts: Dict[str, int] = {}
    for backed in approvals.values():
        for c in backed:
            counts[c] = counts.get(c, 0) + 1
    minded = [v.id for v in voters if model_minded(v)]
    if not counts or not minded:
        return False
    ranked = sorted(counts, key=lambda c: (-counts[c], world.agents[c].born))
    cands = ranked[:POLL_N]
    leader = getattr(world, "leader", "")
    if leader and leader in world.agents and leader not in cands:
        cands = ranked[:POLL_N - 1] + [leader]  # the sitting chief is always on the ballot
    _civic(world)["poll"] = {"tick": world.tick, "reason": reason, "candidates": cands, "voters": minded,
                             "approvals": {k: list(v) for k, v in approvals.items()}, "ballots": {}, "sent": [],
                             "skipped": []}
    return True


def ballot_for(world, voter_id: str) -> List[str]:
    """The candidates a voter chooses between (never itself), in an order of its own: a model leans to the first
    letter, and with one order for everyone the first-listed front-runner took 45 of 55 votes on the 3090."""
    p = poll(world)
    if not p:
        return []
    out = [c for c in p["candidates"] if c != voter_id and c in world.agents]
    return sorted(out, key=lambda c: zlib.crc32(f"{p['tick']}:{voter_id}:{c}".encode()))


def cast(world, voter_id: str, candidate_id: str) -> bool:
    """A voter's mind backed `candidate_id`. The world checks it's still a fair ballot."""
    p = poll(world)
    if not p or voter_id not in p["voters"] or voter_id in p["ballots"] or candidate_id not in ballot_for(world, voter_id):
        return False
    p["ballots"][voter_id] = candidate_id
    return True


def skip(world, voter_id: str) -> None:
    """The voter's mind can't answer (unavailable, or the reply was no use): it votes by the simulator's rule."""
    p = poll(world)
    if p and voter_id in p["voters"] and voter_id not in p["skipped"]:
        p["skipped"].append(voter_id)


def tally(world, p: Dict[str, Any]) -> Dict[str, int]:
    """A model ballot backs one candidate; every other adult (instinct, or a mind that didn't answer) backs everyone it
    likes, as the simulator always has."""
    votes: Dict[str, int] = {}
    for voter, backed in p["approvals"].items():
        if voter not in world.agents:
            continue
        for c in [p["ballots"][voter]] if voter in p["ballots"] else backed:
            if c in world.agents:
                votes[c] = votes.get(c, 0) + 1
    return votes


def tick(world) -> None:
    """Close the poll once every model voter has answered (or can't), or its time is up. Drop stale trade offers."""
    p = poll(world)
    if p:
        live = [v for v in p["voters"] if v in world.agents]
        done = all(v in p["ballots"] or v in p["skipped"] for v in live)
        if done or world.tick - p["tick"] >= POLL_TICKS:
            world.civic["poll"] = None
            world.seat_chief(tally(world, p), p["reason"], ballots=len(p["ballots"]))
    offers = _civic(world).get("offers")
    if offers:
        for k in [k for k, o in offers.items() if world.tick - o["tick"] > OFFER_KEEP]:
            del offers[k]


# ---------------------------------------------------------------------------------------------- trades
def offer_verdict(world, trader: Agent, partner: Agent, give: Dict[str, int], get: Dict[str, int],
                  s: Dict[str, Any]) -> Optional[bool]:
    """Does `partner` take the deal? None: still waiting for its mind's answer (the trader keeps waiting).
    A sleeping or hostile partner refuses without being asked; an instinct partner judges by value."""
    if partner.activity == "sleeping" or partner.affinity.get(trader.id, 0.0) < -20 or not model_minded(partner):
        return world.accepts_trade(partner, trader, give, get)
    offers = _civic(world).setdefault("offers", {})
    o = offers.get(partner.id)
    if s.get("offer") is None:
        if o is not None and o["from"] != trader.id:
            return world.accepts_trade(partner, trader, give, get)  # someone else's offer is being weighed
        s["offer"] = world.tick
        offers[partner.id] = {"from": trader.id, "give": dict(give), "get": dict(get), "tick": world.tick,
                              "sent": False}
        return None
    if o is None or o["from"] != trader.id or o["tick"] != s["offer"]:
        return world.accepts_trade(partner, trader, give, get)  # (the offer was dropped)
    if "answer" in o:
        del offers[partner.id]
        if o["answer"] is None:
            return world.accepts_trade(partner, trader, give, get)
        return bool(o["answer"])
    if world.tick - o["tick"] >= OFFER_TICKS:
        del offers[partner.id]
        return world.accepts_trade(partner, trader, give, get)
    return None


def pending_offer(world, partner_id: str) -> Optional[Dict[str, Any]]:
    o = (_civic(world).get("offers") or {}).get(partner_id)
    return o if o is not None and "answer" not in o else None


def answer_offer(world, partner_id: str, offer_tick: int, accept: Optional[bool]) -> bool:
    """The partner's mind answered (True accept, False refuse, None: no usable answer, judge by value)."""
    o = (_civic(world).get("offers") or {}).get(partner_id)
    if o is None or o["tick"] != offer_tick or "answer" in o:
        return False
    o["answer"] = accept
    return True
