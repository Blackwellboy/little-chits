import inspect

from chits.brain import prompt as P
from chits.brain.llm import BrainConfig
from chits.brain.instinct import Instinct
from chits.sim.world import World


def _world(culture="direct"):
    w = World("A", "A", 1234, culture, 96, 10)
    ins = Instinct()

    def hook(world, a):
        if not a.plan:
            p = ins.plan(world, a)
            a.plan, a.goal = p["steps"], p["goal"]

    for _ in range(600):  # give them memories, knowledge and neighbours
        w.step(hook)
    return w


def test_config_field():
    assert BrainConfig(id="x").prompt_style == "full"
    assert BrainConfig(id="x", prompt_style="compact").prompt_style == "compact"


def test_full_is_default_and_unchanged():
    w = _world()
    a = next(iter(w.agents.values()))
    assert P.messages(w, a) == P.messages(w, a, style="full")
    assert P.messages(w, a)[0]["content"] == P.system_prompt(w, a)


def test_compact_is_short_and_complete():
    w = _world()
    for a in list(w.agents.values())[:5]:
        full = P.messages(w, a, style="full")
        comp = P.messages(w, a, style="compact")
        assert [m["role"] for m in comp] == ["system", "user"]
        assert len(comp[0]["content"]) <= 1400
        assert len(comp[1]["content"]) <= 1800
        lf = sum(len(m["content"]) for m in full)
        lc = sum(len(m["content"]) for m in comp)
        assert lc <= 0.65 * lf, (lc, lf)
        text = comp[0]["content"] + comp[1]["content"]
        assert a.name in text and "plan" in text and '"thought"' in text
        assert "Hunger" in text and "Carrying" in text


def _verbs_line(text):
    lines = [l for l in text.splitlines() if l.startswith("Verbs:")]
    assert len(lines) == 1, "compact system prompt needs exactly one line starting with 'Verbs:'"
    return {v.strip() for v in lines[0][len("Verbs:"):].split(",") if v.strip()}


def test_compact_respects_culture():
    wa, wb = _world("direct"), _world("stigmergy")
    va = _verbs_line(P.messages(wa, next(iter(wa.agents.values())), style="compact")[0]["content"])
    vb = _verbs_line(P.messages(wb, next(iter(wb.agents.values())), style="compact")[0]["content"])
    assert {"gather", "eat", "craft", "experiment", "build", "help", "inspect"} <= vb
    assert {"say", "teach", "write"} <= va
    assert not ({"say", "teach", "write"} & vb)


def test_mind_uses_style():
    from chits.brain import mind

    assert "prompt_style" in inspect.getsource(mind.Mind._ask)
