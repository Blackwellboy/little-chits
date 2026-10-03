"""Presentation themes. `CHITS_THEME=norse` gives new chits and worlds Norse names; nothing else in the world changes.

A theme is presentation only: the simulation draws exactly the same random numbers with it on or off. Chit names
are still drawn by the syllable generator, then shown through a fixed, reversible table, so collisions (which
cost the generator extra draws) are checked against the same syllable names in both cases.
"""

from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from typing import Dict, Sequence, Tuple

THEMES = ("default", "norse")

WORLD_NAMES = {"norse": {"A": "Fjordhaven", "B": "Pineholm"}}


def active() -> str:
    """The theme this process runs with: `CHITS_THEME`, or "default" when unset or unknown."""
    t = os.environ.get("CHITS_THEME", "").strip().lower()
    return t if t in THEMES else "default"


def world_name(wid: str) -> str:
    return WORLD_NAMES.get(active(), {}).get(wid, f"World {wid}")


# ------------------------------------------------------------------ Norse names
# Inspired by Scandinavian names, written in ASCII; the bynames are places, not traits.
# Keep these lists and their order stable: a saved Norse name is read back to its syllable name through them.
GIVEN = (
    "Alf", "Alfhild", "Algot", "Arne", "Arnfinn", "Asa", "Asbjorn", "Asgeir",
    "Aslaug", "Astrid", "Aud", "Bard", "Bergljot", "Birger", "Bjorn", "Bodil",
    "Borghild", "Dag", "Dagny", "Egil", "Einar", "Eirik", "Eivor", "Erling",
    "Estrid", "Finn", "Folke", "Freydis", "Frida", "Geir", "Gerd", "Gisli",
    "Gudmund", "Gudrun", "Gunnar", "Gunnhild", "Gyda", "Hakon", "Halfdan", "Hallgerd",
    "Halvard", "Harald", "Helga", "Helgi", "Herdis", "Hild", "Hjalmar", "Holmfrid",
    "Inga", "Ingeborg", "Ingegerd", "Ingolf", "Ingvar", "Ivar", "Kari", "Ketil",
    "Kolbein", "Leif", "Liv", "Magnus", "Njal", "Odd", "Olaf", "Orm",
    "Orvar", "Ragnhild", "Ragnar", "Rannveig", "Rolf", "Runa", "Runolf", "Sigrid",
    "Sigrun", "Sigurd", "Skardi", "Snorri", "Solveig", "Stein", "Sten", "Stig",
    "Sven", "Thora", "Thorbjorn", "Thord", "Thorfinn", "Thorgerd", "Thorleif", "Thorstein",
    "Thurid", "Thyra", "Toke", "Torsten", "Trygve", "Ulf", "Unn", "Valdis",
    "Vigdis", "Viggo", "Yngvar", "Yrsa",
)
BYNAMES = (
    "", "of the Fjord", "of the Pine", "of the Birch", "of the Shore",
    "of the Holm", "of the Heath", "of the Dale", "of the Ridge", "of the Brook",
    "of the Grove", "of the Meadow", "of the Bay", "of the Cliff", "of the Glen",
    "of the Lake", "of the Marsh", "of the Sound", "of the Strand", "of the Vale",
)
# Compound given names for the longer syllable names a long-lived world falls back to.
PREFIXES = (
    "Arn", "As", "Berg", "Bjorn", "Eld", "Frey", "Geir", "Gud", "Gunn", "Hall", "Hjor", "Hrafn", "Ing",
    "Jarn", "Ketil", "Kol", "Odd", "Ragn", "Sig", "Stein", "Sol", "Thor", "Ulf", "Vig", "Ylv",
)
SUFFIXES = (
    "bjorn", "brand", "dis", "finn", "frid", "gard", "geir", "grim", "hild", "laug",
    "leif", "mund", "ny", "rid", "run", "stein", "ulf", "vald", "veig", "vor",
)

_NUMBERED = re.compile(r"^(.+) ([IVXLCDM]+)$")
_ROMAN = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
          (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))


def roman(n: int) -> str:
    out = ""
    for v, s in _ROMAN:
        while n >= v:
            out, n = out + s, n - v
    return out


def _stable(names) -> list:
    # sha256, never Python's per-process string hash
    return sorted(names, key=lambda n: (hashlib.sha256(n.encode()).digest(), n))


class NorseNames:
    """A one-to-one table between the syllable generator's names and Norse ones.

    Three kinds of syllable name come out of `make_name`: short ("Pilo"), longer ones once the short ones run out
    ("Pimolo"), and numbered ones after that ("Pilo7"). Short names get a given name and byname, longer ones a
    compound given name and byname, and a numbered one its base's Norse name and a Roman numeral ("... VII").
    """

    def __init__(self, syl_a: Sequence[str], syl_b: Sequence[str]):
        short = _stable({(a + b + e).capitalize() for a in syl_a for b in syl_b for e in ("", "o", "a", "i", "y")
                         if 3 <= len(a + b + e) <= 7})
        longer = _stable({(a + c + b).capitalize() for a in syl_a for c in syl_a for b in syl_b
                          if len(a + c + b) <= 9} - set(short))
        simple = list(dict.fromkeys(f"{g} {b}".strip() for b in BYNAMES for g in GIVEN))
        compound = list(dict.fromkeys(f"{p}{s} {b}".strip() for b in BYNAMES for p in PREFIXES for s in SUFFIXES
                                      if p.lower() != s))
        used = set(simple)
        compound = [n for n in compound if n not in used]
        if len(simple) < len(short) or len(compound) < len(longer):
            raise ValueError("the Norse names must cover every syllable name")
        if any(_NUMBERED.match(n) for n in simple + compound):
            raise ValueError("a Norse name must not look numbered")
        self.short = set(short)
        self.forward: Dict[str, str] = {**dict(zip(short, simple)), **dict(zip(longer, compound))}
        self.reverse: Dict[str, str] = {v: k for k, v in self.forward.items()}

    def to_norse(self, name: str) -> str:
        if name in self.forward:
            return self.forward[name]
        base, digits = name.rstrip("0123456789"), name[len(name.rstrip("0123456789")):]
        if base in self.short and digits and int(digits) >= 2 and str(int(digits)) == digits:
            return f"{self.forward[base]} {roman(int(digits))}"
        return name

    def to_syllables(self, name: str) -> str:
        """The syllable name a Norse name stands for. Any other name (an old save's, say) is its own key."""
        if name in self.reverse:
            return self.reverse[name]
        m = _NUMBERED.match(name)
        if m and self.reverse.get(m.group(1)) in self.short:
            k = _from_roman(m.group(2))
            if k >= 2 and roman(k) == m.group(2):
                return f"{self.reverse[m.group(1)]}{k}"
        return name


def _from_roman(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for i, ch in enumerate(s):
        v = vals[ch]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total


@lru_cache(maxsize=4)
def norse_names(syl_a: Tuple[str, ...], syl_b: Tuple[str, ...]) -> NorseNames:
    return NorseNames(syl_a, syl_b)
