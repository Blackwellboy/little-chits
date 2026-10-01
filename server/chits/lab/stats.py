"""Statistics for many-seed comparisons: distributions, not just averages. Pure Python, seeded, no dependencies.

- describe: n, mean, median, sd, min, max
- bootstrap_ci: a percentile bootstrap interval for any statistic (seeded, so a report is reproducible)
- paired: per-seed differences between two arms that shared the seed (the stronger design here: same island)
- cliffs_delta: effect size in [-1, 1], P(a > b) - P(a < b)
- mann_whitney: U and a two-sided p-value (normal approximation with tie correction; unpaired)
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
