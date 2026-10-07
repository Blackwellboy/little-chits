"""Statistics for many-seed comparisons: distributions, not just averages. Pure Python, seeded, no dependencies.

- describe: n, mean, median, sd, min, max
- bootstrap_ci: a percentile bootstrap interval for any statistic (seeded, so a report is reproducible)
- paired: per-seed differences between two arms that shared the seed (the stronger design here: same island)
- cliffs_delta: effect size in [-1, 1], P(a > b) - P(a < b)
- mann_whitney: U and a two-sided p-value (normal approximation with tie correction; unpaired)
- wilcoxon_signed: the Wilcoxon signed-rank test for paired differences. Exact two-sided p for up to 20 non-zero
  pairs (the signed-rank distribution by subset-sum, fractional average ranks made integral by scaling), the usual
  normal approximation with tie correction above. Zeros are dropped (they carry no sign), so n counts non-zero
  pairs; with n of them the smallest exact two-sided p is 2/2**n. Both tails: p = 2*min(P(W+<=w), P(W+>=w)).
- sign_test: the exact two-sided sign test on paired differences (zeros dropped)
- first_day / km_median: time-to-event with censoring (a run that never got there counts, as "not by day N")
"""

from __future__ import annotations

import math
import random
from statistics import mean, median, pstdev
from typing import Callable, Dict, List, Optional, Sequence, Tuple


def describe(xs: Sequence[float]) -> Dict[str, float]:
    xs = list(xs)
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "mean": mean(xs), "median": median(xs), "sd": pstdev(xs) if len(xs) > 1 else 0.0,
            "min": min(xs), "max": max(xs)}


def bootstrap_ci(xs: Sequence[float], stat: Callable[[List[float]], float] = mean, n: int = 2000,
                 alpha: float = 0.05, seed: int = 0) -> Tuple[float, float]:
    xs = list(xs)
    if not xs:
        return (math.nan, math.nan)
    if len(xs) == 1:
        return (xs[0], xs[0])
    rng = random.Random(seed)
    boots = sorted(stat([xs[rng.randrange(len(xs))] for _ in xs]) for _ in range(n))
    lo = boots[int(alpha / 2 * n)]
    hi = boots[min(n - 1, int((1 - alpha / 2) * n))]
    return (lo, hi)


def paired(a: Dict[int, float], b: Dict[int, float], seed: int = 0) -> Dict[str, float]:
    """b - a per seed both have."""
    seeds = sorted(set(a) & set(b))
    d = [b[s] - a[s] for s in seeds]
    if not d:
        return {"n": 0}
    lo, hi = bootstrap_ci(d, seed=seed)
    return {"n": len(d), "mean_diff": mean(d), "median_diff": median(d), "ci_lo": lo, "ci_hi": hi,
            "b_higher": sum(1 for x in d if x > 0), "a_higher": sum(1 for x in d if x < 0), "ties": sum(1 for x in d if x == 0)}


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Positive when b tends to be larger than a."""
    if not a or not b:
        return math.nan
    gt = sum(1 for x in a for y in b if y > x)
    lt = sum(1 for x in a for y in b if y < x)
    return (gt - lt) / (len(a) * len(b))


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> Dict[str, float]:
    """U for a (the count of pairs where a beats b, ties half) and a two-sided p (normal approximation)."""
    n1, n2 = len(a), len(b)
    if not n1 or not n2:
        return {"u": math.nan, "p": math.nan}
    allv = sorted([(x, 0) for x in a] + [(y, 1) for y in b])
    ranks = [0.0] * len(allv)
    i, ties = 0, []
    while i < len(allv):
        j = i
        while j + 1 < len(allv) and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        if j > i:
            ties.append(j - i + 1)
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, allv) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    n = n1 + n2
    tie = sum(t ** 3 - t for t in ties) / (n * (n - 1)) if n > 1 else 0.0
    var = n1 * n2 / 12 * ((n + 1) - tie)
    if var <= 0:
        return {"u": u1, "p": 1.0}
    z = (u1 - n1 * n2 / 2) / math.sqrt(var)
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"u": u1, "p": p}


def _avg_ranks(xs: Sequence[float]) -> List[float]:
    """1-based ranks, ties sharing their average (so 9, 9, 10 ranks 4.5, 4.5, 6)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    return ranks


def wilcoxon_signed(diffs: Sequence[float]) -> Dict[str, float]:
    """The Wilcoxon signed-rank test on paired differences. Zeros are dropped (they carry no sign), so n counts
    non-zero pairs. Ties get average ranks, which can be fractional: the exact distribution scales them to
    integers (average ranks of integers are multiples of 1/2). Two-sided, both tails:
    p = 2*min(P(W+<=w), P(W+>=w)), exact for n <= 20 (the signed-rank distribution by subset-sum), the usual
    normal approximation with tie correction above. With n non-zero pairs the smallest exact two-sided p is 2/2**n."""
    d = [x for x in diffs if x == x and x != 0]
    n = len(d)
    if not n:
        return {"n": 0, "w_plus": math.nan, "p": math.nan, "min_p": math.nan}
    ranks = _avg_ranks([abs(x) for x in d])
    w = sum(r for r, x in zip(ranks, d) if x > 0)
    scale = 2 if any(r != int(r) for r in ranks) else 1
    ri = [int(round(r * scale)) for r in ranks]
    wi = int(round(w * scale))
    if n <= 20:
        # the exact distribution of the signed-rank sum: every sign choice, by subset-sum
        dist = {0: 1}
        for r in ri:
            nxt = dict(dist)
            for s, c in dist.items():
                nxt[s + r] = nxt.get(s + r, 0) + c
            dist = nxt
        total = 2 ** n
        below = sum(c for s, c in dist.items() if s <= wi)
        above = sum(c for s, c in dist.items() if s >= wi)
        p = min(1.0, 2 * min(below, above) / total)
        return {"n": n, "w_plus": w, "p": p, "min_p": 2 / total}
    # normal approximation, tie correction: var = [n(n+1)(2n+1) - sum(t**3 - t)] / 48, in rank units
    i, ties = 0, []
    sr = sorted(ranks)
    while i < n:
        j = i
        while j + 1 < n and sr[j + 1] == sr[i]:
            j += 1
        if j > i:
            ties.append(j - i + 1)
        i = j + 1
    var = (n * (n + 1) * (2 * n + 1) - sum(t ** 3 - t for t in ties)) / 48
    if var <= 0:
        return {"n": n, "w_plus": w, "p": 1.0, "min_p": 0.0}
    z = (w - n * (n + 1) / 4) / math.sqrt(var)
    return {"n": n, "w_plus": w, "p": math.erfc(abs(z) / math.sqrt(2)), "min_p": 0.0}


def sign_test(diffs: Sequence[float]) -> Dict[str, float]:
    """The exact two-sided sign test on paired differences: are the positives and negatives balanced? Zeros
    (ties) are dropped. With n of them, p = 2 * P(X <= min(pos, neg)) under Bin(n, 1/2), clamped to 1."""
    d = [x for x in diffs if x == x and x != 0]
    pos, neg = sum(1 for x in d if x > 0), sum(1 for x in d if x < 0)
    n = len(d)
    if not n:
        return {"n": 0, "pos": 0, "neg": 0, "p": math.nan}
    less = sum(math.comb(n, k) for k in range(min(pos, neg) + 1))
    return {"n": n, "pos": pos, "neg": neg, "p": min(1.0, 2 * less / 2 ** n)}


def first_day(daily: List[Dict[str, float]], metric: str, at_least: float) -> Optional[int]:
    """The first sampled day a run's metric reached `at_least`, or None (censored: not by the end)."""
    for r in daily:
        if r.get(metric, 0) >= at_least:
            return int(r["day"])
    return None


def km_median(times: List[Optional[int]], end: int) -> Optional[float]:
    """Kaplan-Meier median time-to-event; None if fewer than half the runs got there by `end`."""
    events = sorted(t for t in times if t is not None)
    n = len(times)
    at_risk, surv = n, 1.0
    for t in sorted(set(events)):
        d = events.count(t)
        surv *= 1 - d / at_risk
        at_risk -= d
        if surv <= 0.5:
            return float(t)
    return None
