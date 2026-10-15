import { useShallow } from "zustand/react/shallow";
import { useEffect, useState } from "react";
import { api } from "../net/socket";
import { useUI, worlds } from "../state/store";
import type { AgentDetail } from "../types";
import { Portrait } from "./Portrait";
import { ESC_INSPECTOR, onEscape } from "./escape";
import { lifeLines, type LifeEvent } from "./watch";

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

  // Escape closes it: the lowest layer (escape.ts), so an open menu or an armed god tool takes it first; not while a
  // dialog is up over it
  useEffect(() => onEscape(ESC_INSPECTOR, () => {
    const s = useUI.getState();
    if (!s.selected || document.querySelector(".modal-bg")) return false;
    s.set({ selected: null, follow: false });
    return true;
  }), []);

  if (!selected || !detail) return null;
  const close = () => set({ selected: null, follow: false });

  if (detail.kind === "structures") {
    const s = detail;
    return (
      <aside className="inspector">
        <button className="x" onClick={close}>✕</button>
        <h2>{s.name.charAt(0).toUpperCase() + s.name.slice(1)}</h2>
        {s.title && <p className="ambition" title="a chit's own design: it works as the building it is a kind of">💡 {s.inventor ? `${s.inventor}'s idea` : "an invented building"}, a kind of {s.base_name}</p>}
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
  const src = a.plan_source.startsWith("model") ? "model" : "instinct";
  return (
    <aside className="inspector">
      <button className="x" onClick={close}>✕</button>
      <div className="who">
        <div className="portrait"><Portrait hue={a.hue} child={a.child} sleeping={a.act === "sleeping"} tool={a.tool} /></div>
        <div>
          <h2>{(a as any).leader && <span title={`the ${(a as any).leader_title}`}>👑 </span>}{a.name} {!a.alive && <span className="dead">† {a.cause}</span>}</h2>
          <p className="muted">{a.age} days old · gen {a.generation}{a.parents.filter(Boolean).length ? ` · child of ${a.parents.filter(Boolean).join(" & ")}` : ""}</p>
          <p className="traits">{a.personality}</p>
          {a.alive && <div className="row">
            <span className={`src ${src}`} title={a.plan_source}>{src === "model" ? `🧠 ${a.brain_label}` : a.plan_source === "waiting" ? "⏳ waiting for its mind" : a.plan_source === "instinct-filler" ? "⚙ instinct (while it thinks)" : a.plan_source === "instinct-fallback" ? "⚙ instinct (model down)" : "⚙ instinct"}</span>
            <button className={`follow ${follow ? "on" : ""}`} onClick={() => set({ follow: !follow })}>{follow ? "◉ Following" : "◎ Follow"}</button>
          </div>}
        </div>
      </div>
      {!a.alive && (
        <div className="card departed" role="status">
          <b>🕯 {a.name} has died.</b> {a.died >= 0 ? `Day ${Math.floor(a.died / 240) + 1}, ` : ""}{a.cause ? `of ${a.cause}, ` : ""}aged {Math.round(a.age)} days.
          <small className="muted"> This is the record they left: what they knew, who they loved and how their life went.</small>
        </div>
      )}

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
            <h4>{!a.alive ? "Last goal" : a.think ? "💭 thinking about what's next…" : "Goal"}</h4>
            {(a as any).ambition && <p className="ambition" title="A life goal this chit chose for itself">🌟 {(a as any).ambition}</p>}
            {(a as any).origin && <p className="ambition" title="Sailed here from the other island">⛵ from World {(a as any).origin}</p>}
            {(a as any).belief && <p className="ambition" title={`What this chit believes: “${(a as any).belief.tenet}”`}>🕯 {(a as any).belief.name}</p>}
            {a.objective && <p className="objective" title="A lasting objective the chit chose; plans come and go under it">🎯 {a.objective}</p>}
            {a.want && a.alive && <p className="ambition" title="What this chit wants right now: when it comes true it is happier, and better known">💭 wants {a.want}</p>}
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
                  <b>{k.icon} {k.name}</b> <span className="muted">{k.kind === "recipe" ? "make" : "build"}</span>
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
          <LifeStory world={selected.world} id={a.id} alive={a.alive} />
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

type Life = { events: LifeEvent[]; thinned: boolean; born_day: number; died_day: number | null };

/** 🕯 A chit's life, born to died: its notable moments from the events the world recorded (GET .../chits/{id}/life). */
function LifeStory({ world, id, alive }: { world: string; id: string; alive: boolean }) {
  const [life, setLife] = useState<Life | null>(null);
  useEffect(() => {
    let on = true;
    const load = () => api<Life>(`/api/worlds/${world}/chits/${id}/life`).then((l) => on && setLife(l)).catch(() => on && setLife(null));
    load();
    const t = alive ? setInterval(load, 30000) : null;  // (now and then while it lives; a dead chit's story is finished)
    return () => { on = false; if (t) clearInterval(t); };
  }, [world, id, alive]);
  if (!life) return null;
  return (
    <div className="card life-story"><h4>🕯 Life story</h4>
      {life.events.length ? (
        <ol className="life">{lifeLines(life.events).map((l) => (
          <li key={l.seq} className={`imp${l.importance}`}><small>day {l.day}</small><span className="ico">{l.icon}</span><span>{l.text}</span></li>
        ))}</ol>
      ) : <p className="muted small">Nothing recorded yet.</p>}
      {life.thinned && <small className="muted">A long life: the smaller moments are left out.</small>}
    </div>
  );
}

type Kin = { id: string; name: string; alive: boolean; born_day: number; died_day: number | null; cause: string | null };

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

