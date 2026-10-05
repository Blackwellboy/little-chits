"""Tolerant parsing of model replies into plans.

Local models return all sorts: <think> blocks, ```json fences, prose around the
JSON, trailing commas, single quotes, steps as strings ("gather wood x5"), or
the plan nested under odd keys. We accept anything that can be read honestly,
and reject what can't; the world validates every step anyway.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..sim.actions import VERB_ALIASES, VERBS, normalize_verb
from ..sim.items import STATIONS, normalize_item
from ..textcut import clause_cut

_THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)
_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)


class ParseError(ValueError):
    pass


def strip_reasoning(text: str) -> str:
    text = _THINK.sub("", text or "")
    # unterminated think block: keep what follows the last closing tag, or drop it
    if re.search(r"<think>", text, re.I) and not re.search(r"</think>", text, re.I):
        idx = text.rfind("{")
        text = text[idx:] if idx >= 0 else ""
    if "</think>" in text:
        text = text.split("</think>")[-1]
    return text.strip()


def _balanced_objects(text: str) -> List[str]:
    out = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    quote = ""
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'") and depth > 0:
            in_str, quote = True, ch
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(text[start: i + 1])
    if depth > 0 and start >= 0:  # truncated reply (hit max_tokens): close it properly
        out.append(_close_truncated(text[start:]))
    return out


def _close_truncated(frag: str) -> str:
    stack: List[str] = []
    in_str = esc = False
    quote = ""
    for ch in frag:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str, quote = True, ch
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    if in_str:
        frag += quote
    frag = frag.rstrip().rstrip(",").rstrip(":")
    if stack and stack[-1] == "{":
        frag = re.sub(r'([{,])\s*"[^"]*"\s*:?\s*$', r"\1", frag).rstrip(",")
    return frag + "".join("}" if c == "{" else "]" for c in reversed(stack))


def _repair(s: str) -> str:
    s = re.sub(r",\s*([}\]])", r"\1", s)  # trailing commas
    s = re.sub(r"//[^\n]*", "", s)  # line comments
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)
    # single-quoted keys/strings -> double quotes (only when no double quotes are used)
    if '"' not in s and "'" in s:
        s = s.replace("'", '"')
    # unquoted keys
    s = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', s)
    # a colon where the comma belongs: "objective":"somewhere warm":"goal":... (2 of 8 replies from one model;
    # a string value is never followed by a colon in real JSON)
    s = re.sub(r'(:\s*"(?:[^"\\]|\\.)*")\s*:\s*(")', r'\1,\2', s)
    return s


def extract_json(text: str) -> Dict[str, Any]:
    return extract_json_ex(text)[0]


def extract_json_ex(text: str):
    """Like extract_json, but also says whether the reply needed repairing to parse."""
    text = strip_reasoning(text)
    cands: List[str] = []
    for m in _FENCE.finditer(text):
        cands += _balanced_objects(m.group(1))
    cands += _balanced_objects(text)
    # prefer the largest object that parses
    cands.sort(key=len, reverse=True)
    for c in cands:
        for i, attempt in enumerate((c, _repair(c))):
            try:
                v = json.loads(attempt)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(v, dict):
                return v, i > 0
    raise ParseError("no JSON object found in reply")


_STEP_RE = re.compile(r"^\s*([a-zA-Z_ ]+?)\s*(?:\(|:)?\s*(.*?)\)?\s*$")

# These steps do nothing without the thing they act on: the simulator fails each one at once ("None can't be
# gathered from the land", 113 times in the 2026-10-05 live game) and throws the rest of the plan away with it
NEEDS_WHAT = ("gather", "craft", "take")
_STATION_WORDS = {"campfire": "fire", "bench": "workshop", "workbench": "workshop", **{s: s for s in STATIONS}}
_NAME_WORDS = ("name", "named", "call", "called")
_NO_NAME = ("", "it", "them", "this", "that")
_INPUT_FILLER = ("some", "a", "an", "the", "of", "with", "for", "more")


def _verb_tail(raw: Any, verb: str) -> str:
    """The object written into the verb itself: "gather wood" or "gather_berries" -> "wood" / "berries"."""
    s = str(raw or "").strip().lower().replace("-", " ").replace("_", " ")
    if s.replace(" ", "_") in VERBS or s.replace(" ", "_") in VERB_ALIASES:
        return ""  # a verb of two words ("warm up", "pick up")
    words = s.split()
    return " ".join(words[1:]) if len(words) > 1 and normalize_verb(words[0]) == verb else ""


def _split_items(text: str) -> Optional[List[str]]:
    """'berries iron ore' -> ['berries', 'iron ore'], when every word belongs to a known item (longest names first)."""
    words = text.split()
    out: List[str] = []
    i = 0
    while i < len(words):
        for j in range(len(words), i, -1):
            if normalize_item(" ".join(words[i:j])):
                out.append(" ".join(words[i:j]))
                i = j
                break
        else:
            return None
    return out or None


def _inputs(entries: List[Any], step: Dict[str, Any]) -> List[Any]:
    """An experiment's or invention's inputs written as words, read one fixed way. A station named among them ("at
    fire", or last: "berries iron ore fire") becomes the step's "at", "name it"/"called X" its name, and a run of item
    names with no commas between them ("berries iron ore") its items. Anything else is left as written, for the
    simulator to judge."""
    out: List[Any] = []
    for raw in entries:
        if not isinstance(raw, str):
            out.append(raw)
            continue
        words = raw.split()
        low = [w.lower() for w in words]
        if not words:
            continue
        if low[0] in _NAME_WORDS:
            name = " ".join(words[1:])
            if name.lower() not in _NO_NAME:
                step.setdefault("name", name)
            continue
        station = None
        if low[-1] in _STATION_WORDS and (len(low) == 1 or low[-2] == "at" or not normalize_item(" ".join(words))):
            station = _STATION_WORDS[low[-1]]
            words = words[:-2] if len(low) > 1 and low[-2] == "at" else words[:-1]
        text = " ".join(words)
        parts = [text] if normalize_item(text) else _split_items(text)
        if station and (parts or not words):
            step.setdefault("at", station)
            out.extend(parts or [])
        elif parts:
            out.extend(parts)
        else:
            out.append(raw.strip())
    return out


def _step_from_string(s: str) -> Optional[Dict[str, Any]]:
    s = s.strip().strip(".")
    if not s:
        return None
    words = s.replace(":", " ").replace("(", " ").replace(")", " ").split()
    if not words:
        return None
    verb = normalize_verb(words[0])
    if not verb:
        return None
    rest = words[1:]
    step: Dict[str, Any] = {"do": verb}
    qty = None
    clean = []
    for w in rest:
        m = re.match(r"^x?(\d+)x?$", w.lower())
        if m:
            qty = int(m.group(1))
        elif w.lower() not in ("some", "a", "an", "the", "of", "to", "at", "with", "for", "more", "and"):
            clean.append(w)
    if verb in ("experiment", "invent"):
        # (the words "at" and "and" matter here: "berries, iron ore at fire")
        body = " ".join(w for w in rest if not re.match(r"^x?(\d+)x?$", w.lower()))
        segs = [" ".join(w for w in seg.split() if w.lower() not in _INPUT_FILLER)
                for seg in re.split(r",|\+|;|\band\b", body, flags=re.I)]
        step["with"] = _inputs([sg for sg in segs if sg], step) or clean
    elif verb in ("say",):
        step["text"] = " ".join(rest)
    elif verb in ("give", "teach") and clean:
        step["to"] = clean[0]
        if len(clean) > 1:
            step["what"] = " ".join(clean[1:])
    elif verb == "explore" and clean:
        step["dir"] = clean[0]
    elif clean:
        step["what"] = " ".join(clean)
    if qty:
        step["qty"] = qty
    return _complete(step)


def _complete(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The step, or None (rejected, as unreadable steps are) when it lacks the thing it must act on."""
    if step["do"] in NEEDS_WHAT:
        what = step.get("what")
        if not any(v is not None and not isinstance(v, bool) and str(v).strip()
                   for v in (what if isinstance(what, list) else [what])):
            return None
    return step


def _ingredient_map(value: Dict[str, Any]) -> Optional[List[str]]:
    name = next((value[k] for k in ("item", "what", "name") if isinstance(value.get(k), str)), None)
    bag = {name: value.get("qty", value.get("n", value.get("count", 1)))} if name else value
    out = []
    for item, count in bag.items():
        try:
            n = int(count)
            if isinstance(count, bool) or float(count) != n or n <= 0:
                return None
        except (TypeError, ValueError, OverflowError):
            return None
        if not isinstance(item, str) or not item.strip() or len(out) + n > 6:
            return None
        out.extend([item] * n)
    return out or None


def normalize_step(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, str):
        return _step_from_string(raw)
    if not isinstance(raw, dict):
        return None
    d = {str(k).lower(): v for k, v in raw.items()}
    verb_raw = d.pop("do", None) or d.pop("action", None) or d.pop("verb", None) or d.pop("type", None) or d.pop("act", None)
    if verb_raw is None and len(d) == 1:
        # {"gather": "wood"} style
        (k, v), = d.items()
        if normalize_verb(k):
            verb_raw, d = k, {"what": v} if not isinstance(v, dict) else v
    verb = normalize_verb(verb_raw)
    if not verb:
        return None
    step: Dict[str, Any] = {"do": verb}
    # keep only known arg names; map common synonyms
    syn = {
        "item": "what", "items": "with", "resource": "what", "object": "what", "structure": "what",
        "design": "what", "recipe": "what", "knowledge": "what", "amount": "qty", "quantity": "qty",
        "count": "qty", "n": "qty", "target_id": "target", "id": "target", "who": "to", "recipient": "to",
        "agent": "to", "name": "to", "message": "text", "words": "text", "say": "text", "direction": "dir",
        "location": "near", "where": "near", "place": "near", "site_id": "site", "station": "at",
        "ingredients": "with", "materials": "with", "inputs": "with",
    }
    if verb in ("experiment", "invent"):
        nm = d.pop("name", None) or d.pop("call", None) or d.pop("called", None)
        if isinstance(nm, (str, int, float)):
            step["name"] = str(nm)
    if verb == "invent":
        pur = d.pop("purpose", None) or d.pop("for", None) or d.pop("use", None) or d.pop("goal", None)
        if isinstance(pur, (str, int, float)):
            step["purpose"] = str(pur)
    if verb == "sail":
        for k in ("intent", "home"):
            if k in d:
                step[k] = d.pop(k)
    if verb == "trade":
        for k in ("give", "offer", "get", "want", "for"):
            if k in d:
                step.setdefault({"offer": "give", "want": "get", "for": "get"}.get(k, k), d.pop(k))
    for k, v in d.items():
        k2 = syn.get(k, k)
        if k2 in ("what", "with", "qty", "to", "target", "site", "text", "dir", "near", "at"):
            if k2 == "what" and verb in ("experiment", "invent") and isinstance(v, list):
                k2 = "with"
            if k2 in step:
                continue
            step[k2] = v
    if verb in ("experiment", "invent") and "with" not in step and "what" in step:
        step["with"] = step.pop("what")
    if verb in NEEDS_WHAT and step.get("what") in (None, ""):
        tail = _verb_tail(verb_raw, verb)  # {"do": "gather wood"}
        if tail:
            step["what"] = tail
    if verb == "say" and "text" not in step and "what" in step:
        step["text"] = step.pop("what")
    if verb in ("go",) and "to" not in step:
        for k in ("near", "target", "what"):
            if k in step:
                step["to"] = step.pop(k)
                break
    if verb == "build" and "what" not in step and "target" in step:
        step["what"] = step.pop("target")
    if isinstance(step.get("what"), str) and verb not in ("say", "write"):
        m = re.match(r"^\s*(\d{1,2})\s*x?\s+(\S.*)$", step["what"])
        if m:  # "3 seeds"
            step["what"] = m.group(2)
            step.setdefault("qty", m.group(1))
    if "qty" in step:
        try:
            q = float(str(step["qty"]).strip("x "))
            if q != q:  # NaN
                raise ValueError
            step["qty"] = max(1, min(99, int(q)))
        except (ValueError, OverflowError):
            step.pop("qty")
    if verb in ("experiment", "invent"):
        ingredients = step.get("with")
        if isinstance(ingredients, str):  # "berries iron ore fire", "glass, copper ore at furnace"
            ingredients = [x for x in re.split(r",|\+|;|\band\b", ingredients, flags=re.I) if x.strip()]
        if isinstance(ingredients, list):
            ingredients = _inputs(ingredients, step)
        if isinstance(ingredients, dict):
            ingredients = _ingredient_map(ingredients)
            if ingredients is None:
                return None
        if isinstance(ingredients, list):
            flat = []
            for item in ingredients:
                if isinstance(item, dict):
                    items = _ingredient_map(item)
                    if items is None:
                        return None
                    flat.extend(items)
                elif isinstance(item, str):
                    flat.append(item)
                else:
                    return None
            if not flat or len(flat) > 6:
                return None
            step["with"] = flat
    # Never clamp a scientific mixture to a different set of inputs.
    # nothing nested reaches the simulator: a dict value becomes a plain one, or is dropped
    for k in list(step):
        v = step[k]
        if isinstance(v, dict):
            named = next((v[f] for f in ("item", "what", "name") if isinstance(v.get(f), str)), None)
            n = v.get("qty", v.get("n", v.get("count")))
            if verb == "trade" and k in ("give", "get"):
                # the prompt teaches {"stone":3}; flattening it to 3 broke every model trade (0 of 8 ever worked)
                bag = {named: n or 1} if named else {str(i): x for i, x in v.items() if isinstance(x, (int, float, str))}
                step[k] = {i: x for i, x in bag.items() if str(i).strip()}
                if not step[k]:
                    step.pop(k)
                continue
            if named is None and len(v) == 1 and isinstance(next(iter(v.values())), (int, float)):
                named, n = next(iter(v.items()))  # {"seeds": 2}: the item is the key, not the count
            if named is not None:
                step[k] = named
                if k == "what" and n is not None and "qty" not in step:
                    try:
                        step["qty"] = max(1, min(99, int(n)))
                    except (TypeError, ValueError):
                        pass
                continue
            flat = next((x for x in v.values() if isinstance(x, (str, int, float))), None)
            if flat is None:
                step.pop(k)
            else:
                step[k] = flat
        elif isinstance(v, list):
            flat = []
            for x in v:
                if isinstance(x, (str, int, float)):
                    flat.append(x)
                elif isinstance(x, dict):  # {"item": "stone", "qty": 2} -> "stone", "stone"
                    name = next((x[f] for f in ("item", "what", "name") if isinstance(x.get(f), str)), None)
                    try:
                        n = int(x.get("qty") or x.get("n") or 1)
                    except (TypeError, ValueError):
                        n = 1
                    if name:
                        flat += [name] * max(1, min(3, n))
            step[k] = flat[:6]
    return _complete(step)


def parse_plan(text: str, max_steps: int = 6) -> Dict[str, Any]:
    obj, repaired = extract_json_ex(text)
    low = {str(k).lower(): v for k, v in obj.items()}
    plan = None
    for key in ("plan", "steps", "actions", "next_steps", "action_plan", "todo"):
        if key in low:
            plan = low[key]
            break
    if plan is None and ("do" in low or "action" in low):
        plan = [obj]
    if isinstance(plan, dict):
        plan = plan.get("steps") or plan.get("actions") or [plan]
    if isinstance(plan, str):
        plan = [p for p in re.split(r"[;\n]|, then | then ", plan) if p.strip()]
    if not isinstance(plan, list):
        raise ParseError("reply had no plan list")
    steps = []
    rejected = []
    for raw in plan[: max_steps + 4]:
        st = normalize_step(raw)
        if st:
            steps.append(st)
        else:
            rejected.append(raw)
        if len(steps) >= max_steps:
            break
    if not steps:
        raise ParseError(f"no usable steps in plan (got {str(plan)[:120]})")

    def _s(*keys: str) -> str:
        for k in keys:
            v = low.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    return {
        "thought": _s("thought", "thinking", "reasoning", "rationale", "reason", "inner_monologue", "why")[:280],
        "goal": _s("goal", "intent", "aim")[:100],
        "objective": _s("objective", "purpose", "long_term_goal")[:140],
        "say": _s("say", "speech", "message")[:160],
        "job": _job(_s("job", "role", "profession")),
        "steps": steps,
        "rejected": len(rejected),
        "repaired": repaired,
    }


def _job(raw: str) -> str:
    from ..sim.agent import JOBS

    j = (raw or "").strip().lower()
    return j if j in JOBS else ""


def parse_lessons(text: str) -> List[str]:
    return [t for t, _ in parse_lesson_items(text)]


def was_truncated(text: str) -> bool:
    """True when the reply's JSON object never closed: the model hit max_tokens mid-sentence."""
    depth, in_str, esc, opened = 0, False, False, False
    for ch in strip_reasoning(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
            opened = True
        elif ch == "}":
            depth = max(0, depth - 1)
    return opened and depth > 0


def parse_reflection(text: str) -> Dict[str, Any]:
    """A weekly reflection: lessons, plus an ambition (a life goal) the chit may choose or keep."""
    out: Dict[str, Any] = {"lessons": parse_lessons(text), "ambition": "", "truncated": was_truncated(text)}
    try:
        obj = {str(k).lower(): v for k, v in extract_json(text).items()}
    except ParseError:
        obj = {}
    amb = obj.get("ambition") or obj.get("goal") or obj.get("dream") or ""
    amb = str(amb).strip()[:120] if isinstance(amb, (str, int, float)) else ""
    if len(str(obj.get("ambition") or obj.get("goal") or obj.get("dream") or "")) > 120:
        amb = clause_cut(amb)
    out["ambition"] = amb if len(amb) >= 6 else ""
    dec = obj.get("decree") or obj.get("law") or obj.get("rule") or ""
    dec = " ".join(str(dec).split()) if isinstance(dec, (str, int, float)) else ""
    out["decree"] = dec if 8 <= len(dec) <= 120 else ""
    proj = obj.get("project") or obj.get("village_project") or ""  # a chief may set the village's project
    proj = " ".join(str(proj).split()) if isinstance(proj, (str, int, float)) else ""
    out["project"] = proj if 3 <= len(proj) <= 80 else ""
    out["belief"] = None
    raw = obj.get("belief") or obj.get("faith") or obj.get("creed")
    if isinstance(raw, dict):
        r = {str(k).lower(): v for k, v in raw.items()}
        name = r.get("name") or r.get("title") or ""
        tenet = r.get("tenet") or r.get("text") or r.get("belief") or r.get("creed") or ""
        name = str(name).strip() if isinstance(name, (str, int, float)) else ""
        tenet = str(tenet).strip() if isinstance(tenet, (str, int, float)) else ""
        if tenet or name:  # a name alone means joining a belief that already exists
            out["belief"] = {"name": name, "tenet": tenet}
    elif isinstance(raw, str) and raw.strip():
        out["belief"] = {"name": "", "tenet": raw.strip()}
    return out


def parse_lesson_items(text: str) -> List[tuple]:
    """Lessons as (text, cited memory ids). Accepts plain strings or {"text": ..., "from": [ids]} objects."""
    try:
        obj = extract_json(text)
        raw = obj.get("lessons") or obj.get("beliefs") or obj.get("insights") or []
    except ParseError:
        raw = [l.strip("-*• \t") for l in strip_reasoning(text).splitlines() if len(l.strip()) > 8][:3]
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for l in raw:
        cites: List[int] = []
        if isinstance(l, dict):
            src = l.get("from") or l.get("memories") or l.get("sources") or []
            if not isinstance(src, list):
                src = [src]
            for c in src:
                try:
                    cites.append(int(str(c).lstrip("m")))
                except ValueError:
                    pass
            l = l.get("lesson") or l.get("text") or ""
        l = str(l).strip()
        if 6 < len(l) <= 200:
            out.append((l, cites))
    return out[:3]
