"""The comparison pack: a Markdown report plus tidy CSVs (one row per run, one row per run-day). Blind unless asked:
arms appear as their labels, and `unblind` names them only after the seal checks out."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import assign, stats
from .run import invalid, results
from .spec import ExperimentSpec

DEFAULT_METRICS = ["discoveries", "population", "era", "food", "copper", "iron", "villages", "homes", "useful",
                   "births", "forgotten", "tunnels", "loose", "starved", "preventable"]


OPPORTUNITY_ROWS = [("requests per chit-day", "requests_per_chit_day"), ("waiting share", "waiting_share"),
                    ("seconds waited per chit-day", "wait_seconds_per_chit_day"),
                    ("model share of steps", "model_step_share"),
                    ("... from plans the model wrote", "model_authored_step_share"),
                    ("body reflex share of steps", "reflex_step_share"),
                    ("routine share of steps", "routine_step_share"),
                    ("heuristic instinct share of steps", "instinct_step_share"),
                    ("strategic plans the model decided", "model_strategic_share"),
                    ("... and wrote itself", "model_authored_strategic_share"),
                    ("steps carried out as another (redirects; a total per run, not per chit-day)", "redirects")]


def by_label(a: Dict[str, Any], label: str) -> List[Dict[str, Any]]:
    return [r for r in a["runs"] if r["label"] == label]


def _fmt(x: float) -> str:
    if x is None or x != x:
        return "-"
    return f"{x:,.2f}" if abs(x) < 100 else f"{x:,.0f}"


def analyze(out, unblind: bool = False) -> Dict[str, Any]:
    out = Path(out)
    manifest = json.loads((out / "manifest.json").read_text())
    spec = ExperimentSpec.from_dict(manifest["protocol"])
    if spec.fingerprint() != manifest["fingerprint"]:
        raise ValueError("the manifest's protocol doesn't match its fingerprint")
    names = assign.unblind(out) if unblind else {}
    runs = results(out)
    labels = sorted({r["label"] for r in runs})
    show = {l: (f"{l} ({names[l]})" if unblind else l) for l in labels}
    metrics = spec.metrics or DEFAULT_METRICS
    by = {l: {r["seed"]: r for r in runs if r["label"] == l} for l in labels}
    table = {}
    for m in metrics:
        table[m] = {}
        for l in labels:
            xs = [r["final"].get(m, 0) for r in by[l].values()]
            d = stats.describe(xs)
            d["ci"] = stats.bootstrap_ci(xs, seed=1)
            table[m][l] = d
    ref = labels[0] if labels else None
    pairs = {}
    for l in labels[1:]:
        pairs[l] = {}
        for m in metrics:
            a = {s: r["final"].get(m, 0) for s, r in by[ref].items()}
            b = {s: r["final"].get(m, 0) for s, r in by[l].items()}
            p = stats.paired(a, b, seed=2)
            p["cliffs_delta"] = stats.cliffs_delta(list(a.values()), list(b.values()))
            p["mann_whitney_p"] = stats.mann_whitney(list(a.values()), list(b.values()))["p"]
            pairs[l][m] = p
    events = {}
    for name, ev in spec.events.items():
        events[name] = {}
        for l in labels:
            times = [stats.first_day(r["daily"], ev["metric"], ev["at_least"]) for r in by[l].values()]
            events[name][l] = {"reached": sum(1 for t in times if t is not None), "runs": len(times),
                               "km_median_day": stats.km_median(times, spec.days)}
    # runs that broke a hard invariant: never in a mean or a paired difference. Blind, the report reads only their
    # redacted records (invalid.json); unblinded, the raw ones (invalid-sealed.json), names and all
    bad = [{k: b.get(k) for k in ("seed", "label", "kind", "what", "tick", "day", "breaks")}
           | ({"arm": names.get(b["label"])} if unblind else {}) for b in invalid(out, sealed=unblind)]
    return {"spec": spec, "manifest": manifest, "labels": labels, "show": show, "metrics": metrics, "table": table,
            "pairs": pairs, "ref": ref, "events": events, "runs": runs, "unblinded": unblind, "invalid": bad}


def markdown(a: Dict[str, Any]) -> str:
    spec, man, show = a["spec"], a["manifest"], a["show"]
    n = len(a["runs"])
    total = len(spec.seeds) * len(spec.arms)
    bad = a.get("invalid") or []
    retried = sum(1 for r in a["runs"] if r.get("invalid_attempts"))
    if bad:
        done = (f"Runs finished: {n} of {total} ({len(bad)} invalid: they broke a hard invariant and are left out of "
                "every mean and difference)." + ("" if n + len(bad) == total else " **Incomplete: resume before drawing "
                                                                                  "conclusions.**"))
    else:
        done = f"Runs finished: {n} of {total}." + ("" if n == total else " **Incomplete: resume before drawing conclusions.**")
    if retried:
        done += f" {retried} run(s) retried after an invalid attempt (`resume --retry-invalid`; the attempts are kept)."
    L = [f"# {spec.name}", "",
         f"Protocol `{man['fingerprint']}` · code `{man['commit']}` · {len(spec.seeds)} seeds × {len(spec.arms)} arms · "
         f"{spec.days} days · island {spec.size} · {spec.population} founders · {spec.contract} contract",
         done,
         ("Arms are **unblinded** (seal checked)." if a["unblinded"] else
          "Arms are shown **blind** by label; `analyze --unblind` names them after checking the seal."), ""]
    if bad:
        L += ["## Invalid runs", "",
              "A run that broke a hard invariant isn't a result. Final values leave it out, and every paired difference "
              "involving its arm leaves its seed out. Its record is `runs/<seed>_<label>/invalid.json` (blind: "
              "the arm's model and servers are named by its label) with every break and its last model calls; the "
              "raw record, `invalid-sealed.json`, is for after unblinding.", "",
              "| seed | arm | day | invariant | what | breaks |", "|---|---|---|---|---|---|"]
        for b in bad:
            arm = f"{b['label']} ({b['arm']})" if a["unblinded"] else b["label"]
            L.append(f"| {b['seed']} | {arm} | {b['day']} | {b['kind']} | {b['what']} | {b.get('breaks') or 1} |")
        L.append("")
    if spec.interventions:
        L += ["Interventions, identical in every arm: " + "; ".join(f"day {i.day} {i.kind}" for i in spec.interventions), ""]
    L += ["## Final values", "", "| metric | " + " | ".join(show[l] for l in a["labels"]) + " |",
          "|---|" + "---|" * len(a["labels"])]
    for m in a["metrics"]:
        cells = []
        for l in a["labels"]:
            d = a["table"][m][l]
            cells.append("-" if not d.get("n") else f"{_fmt(d['mean'])} [{_fmt(d['ci'][0])}, {_fmt(d['ci'][1])}] · med {_fmt(d['median'])}")
        L.append(f"| {m} | " + " | ".join(cells) + " |")
    L += ["", "Mean [95% bootstrap interval] · median, over seeds.", ""]
    for l, per in a["pairs"].items():
        L += [f"## {show[l]} vs {show[a['ref']]}", "",
              "| metric | mean diff per seed [95% CI] | seeds higher / lower / tied | Cliff's delta | Mann-Whitney p |",
              "|---|---|---|---|---|"]
        for m, p in per.items():
            if not p.get("n"):
                continue
            L.append(f"| {m} | {_fmt(p['mean_diff'])} [{_fmt(p['ci_lo'])}, {_fmt(p['ci_hi'])}] | "
                     f"{p['b_higher']} / {p['a_higher']} / {p['ties']} | {_fmt(p['cliffs_delta'])} | {_fmt(p['mann_whitney_p'])} |")
        L += ["", "Differences are paired by seed (both arms had the same island). p-values are not corrected for the "
                  "number of metrics: read them as a guide, not a verdict.", ""]
    if any(r.get("compute") or any(r["final"].get(k) is not None for _, k in OPPORTUNITY_ROWS) for r in a["runs"]):
        L += ["## Thinking opportunities", "",
              "Per chit-day (one chit alive for one day). Reported, not equalised: a model whose plans run out sooner "
              "asks more often. Waiting is the share of a model-minded chit's time spent waiting for its answer "
              "(near 0 in lockstep, where the world waits instead); seconds waited is that lockstep wait in wall time, a cost "
              "of the card and the model, not a world fact; model steps are the finished steps that came from the "
              "model's plans; the rest are body reflexes, routine upkeep and heuristic instinct (docs/PROVENANCE.md). "
              "Shares are of finished steps or strategic plans, not per chit-day; redirects are a total per run.",
              "", "| | " + " | ".join(show[l] for l in a["labels"]) + " |", "|---|" + "---|" * len(a["labels"])]
        for name, key in OPPORTUNITY_ROWS:
            cells = []
            for l in a["labels"]:
                runs = by_label(a, l)
                xs = [x for x in (r["final"].get(key) for r in runs) if x is not None]
                # (a run recorded before a field existed has none: a mean over fewer runs says how many)
                cells.append((_fmt(sum(xs) / len(xs)) + (f" ({len(xs)} of {len(runs)} runs)" if len(xs) < len(runs) else ""))
                             if xs else "-")
            L.append(f"| {name} | " + " | ".join(cells) + " |")
        L += ["", "Means over seeds.", ""]
    if a["events"]:
        L += ["## Time to event", "", "| event | " + " | ".join(show[l] for l in a["labels"]) + " |",
              "|---|" + "---|" * len(a["labels"])]
        for name, per in a["events"].items():
            cells = [f"{per[l]['reached']}/{per[l]['runs']} · median day {_fmt(per[l]['km_median_day'])}" for l in a["labels"]]
            L.append(f"| {name} | " + " | ".join(cells) + " |")
        L += ["", "Median day by Kaplan-Meier: a run that never got there counts as \"not by the last day\"; '-' means "
                  "fewer than half got there.", ""]
    return "\n".join(L)


def write_pack(out, unblind: bool = False) -> Path:
    """Report plus final-state, lifetime-event and daily tidy CSVs (blind/unblinded)."""
    out = Path(out)
    a = analyze(out, unblind)
    tag = "unblinded" if unblind else "blind"
    (out / f"report-{tag}.md").write_text(markdown(a))
    name = assign.unblind(out) if unblind else {}
    with open(out / f"runs-{tag}.csv", "w", newline="") as f:
        cols = sorted({k for r in a["runs"] for k in r["final"]})
        w = csv.writer(f)
        w.writerow(["seed", "arm", "wall_s", *cols])
        for r in a["runs"]:
            w.writerow([r["seed"], name.get(r["label"], r["label"]), r["wall_s"], *[r["final"].get(c, "") for c in cols]])
    # One row per run of persistent event totals. A migrated old save can honestly say that its counters begin
    # after tick 0; fresh Lab worlds are complete_from_start.
    with open(out / f"lifetime-{tag}.csv", "w", newline="") as f:
        event_cols = sorted({k for r in a["runs"] for k in (r.get("lifetime") or {}).get("events", {})})
        w = csv.writer(f)
        w.writerow(["seed", "arm", "since_tick", "through_tick", "complete_from_start", *event_cols])
        for r in a["runs"]:
            life = r.get("lifetime") or {}
            events = life.get("events") or {}
            w.writerow([r["seed"], name.get(r["label"], r["label"]), life.get("since_tick", ""),
                        life.get("through_tick", ""), life.get("complete_from_start", ""),
                        *[events.get(c, 0) for c in event_cols]])
    with open(out / f"daily-{tag}.csv", "w", newline="") as f:
        cols = sorted({k for r in a["runs"] for row in r["daily"] for k in row})
        w = csv.writer(f)
        w.writerow(["seed", "arm", *cols])
        for r in a["runs"]:
            for row in r["daily"]:
                w.writerow([r["seed"], name.get(r["label"], r["label"]), *[row.get(c, "") for c in cols]])
    return out / f"report-{tag}.md"
