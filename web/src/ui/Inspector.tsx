import { useShallow } from "zustand/react/shallow";
import { useEffect, useState } from "react";
import { api, errorText } from "../net/socket";
import { useUI, worlds } from "../state/store";
import type { AgentDetail } from "../types";
import { Portrait } from "./Portrait";

const HOW: Record<string, string> = {
  instinct: "born knowing", discovered: "discovered it", insight: "had the idea", taught: "was taught",
  observed: "watched someone", inspected: "reverse-engineered", read: "read a tablet", built: "helped build one",
};
const HOW_ICON: Record<string, string> = {
  instinct: "·", discovered: "✦", insight: "💡", taught: "🗣", observed: "👀", inspected: "🔍", read: "📜", built: "🔨",
};

function Bar({ label, v, color }: { label: string; v: number; color: string }) {
  return (
    <div className="bar">
      <span>{label}</span>
      <div className="track"><i style={{ width: `${Math.max(0, Math.min(100, v))}%`, background: color }} /></div>
      <b>{Math.round(v)}</b>
    </div>
  );
}

export function Inspector() {
  const { selected, follow, set } = useUI(useShallow((s) => ({ selected: s.selected, follow: s.follow, set: s.set })));
  const [detail, setDetail] = useState<any>(null);
  const [tab, setTab] = useState<"mind" | "knows" | "life">("mind");
  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    let alive = true;
    const kind = selected.id.startsWith("a") ? "agents" : "structures";
    const load = () => api(`/api/worlds/${selected.world}/${kind}/${selected.id}`).then((d) => alive && setDetail({ kind, ...d })).catch(() => alive && setDetail(null));
    load();
    const t = setInterval(load, 1000);
    return () => { alive = false; clearInterval(t); };
  }, [selected?.world, selected?.id]);

  if (!selected || !detail) return null;
  const close = () => set({ selected: null, follow: false });

  if (detail.kind === "structures") {
    const s = detail;
    return (
      <aside className="inspector">
        <button className="x" onClick={close}>✕</button>
        <h2>{s.name.charAt(0).toUpperCase() + s.name.slice(1)}</h2>
        <p className="muted">{s.blurb}</p>
        <div className="kv">
          <span>Status</span><b>{!s.complete ? `under construction · ${Math.round(s.progress * 100)}%` : s.ruined ? "in ruins" : `condition ${Math.round(s.durability)}%`}</b>
          <span>Founded by</span><b>{s.founder ?? "—"} · day {s.created_day}</b>
          {s.completed_day && <><span>Finished</span><b>day {s.completed_day}</b></>}
          <span>Built by</span><b>{s.builder_names.join(", ") || "—"}</b>
          {s.design === "campfire" && <><span>Fire</span><b>{s.lit ? `burning · fuel ${s.fuel}` : "burned out"}</b></>}
          {s.design === "farm" && <><span>Crop</span><b>{!s.planted ? "empty — needs seeds" : s.growth >= 1 ? "ripe!" : `growing ${Math.round(s.growth * 100)}%`}</b></>}
          {s.residents?.length > 0 && <><span>Home of</span><b>{s.residents.join(", ")}</b></>}
          {(s.working || s.workers?.length > 0) && <><span>At work</span><b>{s.workers?.length ? s.workers.join(", ") : "a shift is under way"}</b></>}
        </div>
        {s.produced && Object.keys(s.produced).length > 0 && (
          <div className="card"><h4>Made here</h4>{Object.entries(s.produced).sort((a: any, b: any) => b[1] - a[1]).map(([k, n]) => <span key={k} className="chip">{n as number} {s.item_names?.[k] ?? k.replace(/_/g, " ")}</span>)}</div>
        )}
        {!s.complete && Object.keys(s.needs).length > 0 && (
          <div className="card"><h4>Still needs</h4>{Object.entries(s.needs).map(([k, n]) => <span key={k} className="chip">{n as number} {s.item_names?.[k] ?? k.replace(/_/g, " ")}</span>)}</div>
        )}
        {s.storage && (
          <div className="card"><h4>Stored ({s.stored})</h4>{Object.entries(s.storage).sort((a: any, b: any) => b[1] - a[1]).map(([k, n]) => <span key={k} className="chip">{n as number} {s.item_names?.[k] ?? k.replace(/_/g, " ")}</span>)}</div>
        )}
        {s.shelf?.length > 0 && <div className="card"><h4>Tablets on the shelf</h4>{s.shelf.map((t: string, i: number) => <p key={i} className="tablet">📜 {t}</p>)}</div>}
      </aside>
    );
  }

  const a = detail as AgentDetail;
  const src = a.plan_source.startsWith("model") ? "model" : a.plan_source === "player" ? "player" : "instinct";
  return (
    <aside className="inspector">
      <button className="x" onClick={close}>✕</button>
      <div className="who">
        <div className="portrait"><Portrait hue={a.hue} child={a.child} sleeping={a.act === "sleeping"} tool={a.tool} /></div>
        <div>
          <h2>{(a as any).leader && <span title={`the ${(a as any).leader_title}`}>👑 </span>}{a.name} {!a.alive && <span className="dead">† {a.cause}</span>}</h2>
          <p className="muted">{a.age} days old · gen {a.generation}{a.parents.filter(Boolean).length ? ` · child of ${a.parents.filter(Boolean).join(" & ")}` : ""}</p>
          <p className="traits">{a.personality}</p>
          <div className="row">
            <span className={`src ${src}`} title={a.plan_source}>{src === "player" ? "🎮 player order" : src === "model" ? `🧠 ${a.brain_label}` : a.plan_source === "waiting" ? "⏳ waiting for its mind" : a.plan_source === "instinct-filler" ? "⚙ instinct (while it thinks)" : a.plan_source === "instinct-fallback" ? "⚙ instinct (model down)" : "⚙ instinct"}</span>
            {a.alive && <button className={`follow ${follow ? "on" : ""}`} onClick={() => set({ follow: !follow })}>{follow ? "◉ Following" : "◎ Follow"}</button>}
          </div>
        </div>
      </div>

      <ControlStrip key={a.id} world={selected.world} id={a.id} possessed={a.possessed} alive={a.alive} />

      {a.alive && (
        <div className="needs">
          <Bar label="Food" v={a.needs.hunger} color="linear-gradient(90deg,#f2994a,#f2c94c)" />
          <Bar label="Energy" v={a.needs.energy} color="linear-gradient(90deg,#56ccf2,#2f80ed)" />
          <Bar label="Warmth" v={a.needs.warmth} color="linear-gradient(90deg,#eb5757,#f2994a)" />
          <Bar label="Health" v={a.needs.health} color="linear-gradient(90deg,#27ae60,#6fcf97)" />
        </div>
      )}

      <div className="tabs">
        {(["mind", "knows", "life"] as const).map((t) => <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{t === "mind" ? "Mind" : t === "knows" ? `Knows (${a.knows.length})` : "Life"}</button>)}
      </div>

      {tab === "mind" && (
        <>
          {a.thought && <blockquote className="thought">“{a.thought}”</blockquote>}
          <div className="card">
            <h4>{a.think ? "💭 thinking about what's next…" : "Goal"}</h4>
            {(a as any).ambition && <p className="ambition" title="A life goal this chit chose for itself">🌟 {(a as any).ambition}</p>}
            {(a as any).origin && <p className="ambition" title="Sailed here from the other island">⛵ from World {(a as any).origin}</p>}
            {(a as any).belief && <p className="ambition" title={`What this chit believes: “${(a as any).belief.tenet}”`}>🕯 {(a as any).belief.name}</p>}
            {a.objective && <p className="objective" title="A lasting objective the chit chose; plans come and go under it">🎯 {a.objective}</p>}
            {a.want && <p className="ambition" title="What this chit wants right now: when it comes true it is happier, and better known">💭 wants {a.want}</p>}
            {(a.renown ?? 0) > 0 && <p className="ambition" title="Standing in the village: discoveries, work on village projects, teaching, wishes come true">⭐ renown {a.renown}{a.famous ? " · the village's most renowned: others near it follow its lead" : ""}</p>}
            <FamilyCard world={selected.world} id={a.id} />
            <p className="goal">{a.goal || "—"}</p>
            <ol className="plan">
              {a.plan_state.map((p, i) => (
                <li key={i} className={i === 0 ? "now" : ""}>{p.desc}{p.reflex && <em> reflex</em>}{p.filler && <em> while thinking</em>}</li>
              ))}
            </ol>
            {a.last_result && <p className="result">↳ {a.last_result}</p>}
          </div>
          {a.last_choice && a.last_choice.options.length > 0 && (
            <div className="card weighed" title="How its model weighed the options its body offered (one-token choice, JEV-style)">
              <h4>🧠 What it weighed{a.last_choice.escalated ? " · then wrote its own plan" : ""}</h4>
              {a.last_choice.options.map((o) => (
                <div key={o.letter} className={`opt ${o.letter === a.last_choice!.chose ? "chosen" : ""}`}>
                  <span className="lbl">{o.letter}) {o.goal}</span>
                  <span className="bar"><i style={{ width: `${Math.round(o.p * 100)}%` }} /></span>
                  <span className="pct">{Math.round(o.p * 100)}%</span>
                </div>
              ))}
              {a.last_choice.escalated && a.last_choice.why && <p className="muted">↳ escalated: {a.last_choice.why}</p>}
            </div>
          )}
          <div className="card">
            <h4>Carrying {a.load}/{a.capacity}</h4>
            <div className="inv">{a.inventory.length ? a.inventory.map((it) => <span key={it.key} className={`chip ${it.tool ? "tool" : ""}`}>{it.icon} {it.n > 1 ? `${it.n} ` : ""}{it.name}</span>) : <span className="muted">nothing</span>}</div>
          </div>
          {a.lessons.length > 0 && (
            <div className="card"><h4>Lessons learned</h4><ul className="lessons">{a.lessons.map((l, i) => {
              const src = (a as any).lesson_sources?.[l];
              const unsupported = Array.isArray(src) && src.length === 0;
              return <li key={i} className={unsupported ? "unsupported" : ""} title={unsupported ? "This lesson doesn't cite any real memory" : src ? `from memories ${src.map((x: number) => "m" + x).join(", ")}` : ""}>{l}{unsupported && <em> (unsupported)</em>}</li>;
            })}</ul></div>
          )}
        </>
      )}

      {tab === "knows" && (
        <div className="card">
          <ul className="knows">
            {a.knows.map((k) => (
              <li key={k.key} title={k.detail}>
                <span className="kicon">{HOW_ICON[k.how] ?? "·"}</span>
                <div>
                  <b>{k.icon} {k.name}</b> <span className="muted">{k.kind === "design" ? "build" : "make"}</span>
                  <small>{HOW[k.how] ?? k.how}{k.from ? ` (${k.from})` : ""} · day {k.day} — {k.detail}</small>
                </div>
              </li>
            ))}
          </ul>
          {a.failed.length > 0 && <><h4>Failed experiments</h4><p className="muted small">{a.failed.join(" · ")}</p></>}
        </div>
      )}

      {tab === "life" && (
        <>
          {a.relations.length > 0 && (
            <div className="card"><h4>Relationships</h4>
              {a.relations.map((r) => (
                <div key={r.id} className="rel" onClick={() => set({ selected: { world: selected.world, id: r.id } })}>
                  <span>{r.name}</span><div className="track"><i style={{ width: `${Math.abs(r.affinity)}%`, background: r.affinity > 0 ? "#f78fb3" : "#8395a7" }} /></div><b>{r.affinity > 40 ? "♥" : r.affinity < -10 ? "✗" : ""}</b>
                </div>
              ))}
            </div>
          )}
          <div className="card"><h4>Skills</h4>{Object.entries(a.skills).map(([k, v]) => <Bar key={k} label={k} v={v} color="#bb86fc" />)}</div>
          <div className="card"><h4>Memories</h4>
            <ul className="mem">{a.memories.map((m, i) => <li key={i} className={`imp${m.importance}`}><small>d{Math.floor(m.tick / 240) + 1}</small> {m.text}</li>)}</ul>
          </div>
        </>
      )}
    </aside>
  );
}

export function flyToAgent(world: string, id: string) {
  const w = worlds[world];
  const a = w?.agents.get(id);
  if (a) useUI.getState().set({ focus: { world, x: a.x + 0.5, y: a.y + 0.5, t: Date.now() }, selected: { world, id } });
}

type Kin = { id: string; name: string; alive: boolean; born_day: number; died_day: number | null; cause: string | null };

/** 🎮 Possess: one chit per world can be controlled by clicking age-gate orders, or a short line of text. */
function ControlStrip({ world, id, possessed, alive }: { world: string; id: string; possessed?: boolean; alive: boolean }) {
  const [held, setHeld] = useState(!!possessed);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [last, setLast] = useState("");
  useEffect(() => { setHeld(!!possessed); }, [possessed]);  // (the detail refreshes every second: another chit may take over)
  if (!alive) return null;

  const order = (action: string) =>
    api(`/api/worlds/${world}/agents/${id}/order`, { action })
      .then((r: any) => { setMsg(""); setLast(r.goal || (action === "cancel" ? "side quest dropped" : "")); })
      .catch((e) => setMsg(errorText(e)));
  const send = () => {
    const t = text.trim();
    if (!t) return;
    setText("");
    api(`/api/worlds/${world}/agents/${id}/order`, { text: t })
      .then((r: any) => { setMsg(""); if (r.goal) setLast(r.goal); })
      .catch((e) => setMsg(errorText(e)));
  };
  const possess = () => api(`/api/worlds/${world}/agents/${id}/possess`, {})
    .then(() => { setHeld(true); setMsg(""); }).catch((e) => setMsg(errorText(e)));
  const release = () => api(`/api/worlds/${world}/possess/release`, {})
    .then(() => { setHeld(false); setLast(""); setMsg(""); }).catch((e) => setMsg(errorText(e)));

  const BUTTONS: [string, string, string][] = [
    ["⛏ Mine", "mine", "Gather the raw material the road to the next age needs most"],
    ["🔥 Smelt", "smelt", "Turn ore into copper or iron at a furnace"],
    ["⚒ Forge", "forge", "Work the forge into the next metal part (steel, gear…)"],
    ["🏗 Build", "build", "Build the next building the road needs"],
    ["📖 Teach", "teach", "Teach a recipe or design someone else lacks"],
    ["📦 Haul", "haul", "Carry materials to where they're needed"],
    ["✖ Cancel sidequest", "cancel", "Drop the current plan, pending plan and objective"],
  ];

  return (
    <div className="control">
      {!held ? (
        <button className="follow possess" onClick={possess}>🎮 Possess</button>
      ) : (
        <>
          <div className="control-btns">
            {BUTTONS.map(([label, act, tip]) => <button key={act} title={tip} onClick={() => order(act)}>{label}</button>)}
          </div>
          <div className="row control-tell">
            <input placeholder="tell it… (e.g. mine iron)" value={text} onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
            <button onClick={send}>Go</button>
            <button className="release" onClick={release}>Release</button>
          </div>
        </>
      )}
      {(msg || last) && <p className={`control-msg${msg ? " err" : ""}`}>{msg || `↳ ${last}`}</p>}
    </div>
  );
}

/** 👪 A chit's family, living and dead: click a name to go to them. */
function FamilyCard({ world, id }: { world: string; id: string }) {
  const [fam, setFam] = useState<Record<string, Kin[]> | null>(null);
  const set = useUI((s) => s.set);
  useEffect(() => {
    let alive = true;
    api(`/api/worlds/${world}/family/${id}`).then((f) => alive && setFam(f)).catch(() => alive && setFam(null));
    return () => { alive = false; };
  }, [world, id]);
  if (!fam) return null;
  const groups: [string, string][] = [["grandparents", "Grandparents"], ["parents", "Parents"], ["siblings", "Brothers and sisters"],
    ["children", "Children"], ["grandchildren", "Grandchildren"]];
  const shown = groups.filter(([k]) => (fam[k] || []).length);
  if (!shown.length) return null;
  return (
    <div className="card family"><h4>👪 Family</h4>
      {shown.map(([k, label]) => (
        <div key={k} className="kin"><small className="muted">{label}: </small>
          {(fam[k] as Kin[]).map((p, i) => (
            <span key={p.id}>{i > 0 && ", "}<a className={p.alive ? "" : "dead"} title={p.alive ? `born day ${p.born_day}` : `died day ${p.died_day} (${p.cause})`}
              onClick={() => set({ selected: { world, id: p.id } })}>{p.alive ? "" : "† "}{p.name}</a></span>
          ))}
        </div>
      ))}
    </div>
  );
}

