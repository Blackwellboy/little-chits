"""Which model each world is thinking with, for the desktop launcher (scripts/desktop.sh report_brains).

Reads the running game's /api/brains JSON on stdin and prints one @ok/@warn line per world. MODELS (env) holds the
GPU script's "# model PORT NAME LOG" lines, to name the card a port belongs to. (It used to be a program inside a
single-quoted bash string, where speed['text'] closed the quotes: a slow model crashed the report with a NameError.)
"""

import json
import os
import sys


def report(d, models: str = "") -> list:
    names = {}
    for line in models.splitlines():
        p = line.split()
        if len(p) >= 2:
            names[p[0]] = p[1]
    by_id = {b["config"]["id"]: b for b in d.get("brains", [])}
    out = []
    for wid, bid in sorted((d.get("assign") or {}).items()):
        b = by_id.get(bid)
        if not b:
            out.append(f"@warn w{wid} World {wid} has no model, so it runs on instinct (pick one in the game: Brains).")
            continue
        url = b["config"]["base_url"]
        port = url.rsplit(":", 1)[-1].split("/")[0]
        card = f" on the {names[port]}" if port in names else ""
        model = b["stats"].get("resolved_model") or b["config"].get("model") or url
        speed = b.get("speed") or {}
        if b.get("healthy") and speed.get("level") == "slow":
            out.append(f"@warn w{wid} World {wid} thinks with {model}{card}. {speed.get('text', '')}".rstrip())
        elif b.get("healthy"):
            out.append(f"@ok w{wid} World {wid} thinks with {model}{card}.")
        else:
            out.append(f"@warn w{wid} World {wid} should use {model}{card}, but it isn't answering yet.")
    return out


if __name__ == "__main__":
    for line in report(json.load(sys.stdin), os.environ.get("MODELS", "")):
        print(line)
