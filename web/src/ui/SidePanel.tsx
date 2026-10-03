import { useShallow } from "zustand/react/shallow";
import { useEffect, useMemo, useState } from "react";
import { api, authedUrl } from "../net/socket";
import { localStorageSet, useUI, worlds, type Tab } from "../state/store";
import type { Stats, WorldEvent } from "../types";
import { Portrait } from "./Portrait";
import { WHY_NOTHING, whyLines, type WhyData } from "./why";

const KIND_ICON: Record<string, string> = {
  storyteller: "📣", wolf: "🐺", wolf_driven_off: "🛡", discovery: "✦", first: "★", learned: "💡", built: "🏠", site: "📐", helped: "🤝", birth: "🍼", death: "🕯",
  speech: "💬", gift: "🎁", tablet: "📜", legacy: "📜", season: "🗓", ruin: "🏚", restored: "🔧", harvest: "🌾",
  reflection: "🪞", fire_out: "🔥", fire_lit: "🔥", crafted: "🛠", produced: "⚒", tool_broke: "🪓", note: "·",
  invention: "💡", belief: "🕯", convert: "🙏", scripture: "📜", era: "🏛", launch: "🚀", job: "🧰", trade: "🤝",
  money: "🪙", election: "🗳", elder: "👑", law: "📜", theft: "🫳", caught: "🛡", fight: "💢", militia: "🛡",
  miracle: "🪄", revelation: "👽", artifact: "✨", ambition: "🌟", objective: "🎯", sign: "🪧", settlement: "🏘",
  storm: "⛈", weather: "🌦", timeline: "⑂", voyage: "⛵", arrival: "🏝",
  project: "🏗", project_done: "🏆", hint: "📚", hint_true: "💡", wish: "🌟", last_keeper: "⏳", forgotten: "🕳",
};

function usePoll<T>(fn: () => Promise<T>, ms: number, deps: any[]): T | null {
  const [v, setV] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    const go = () => fn().then((x) => alive && setV(x)).catch(() => {});
    go();
    const t = setInterval(go, ms);
    return () => { alive = false; clearInterval(t); };
  }, deps);
  return v;
}

export function SidePanel() {
  const { tab, view, set, worlds: metas } = useUI(useShallow((s) => ({ tab: s.tab, view: s.view, set: s.set, worlds: s.worlds })));
  const [pick, setPick] = useState<string>(() => { try { return localStorage.getItem("chits:panelWorld") || "A"; } catch { return "A"; } });
  // in split view the chronicle and people lists can show either world
  const primary = view === "split" ? (metas.some((m) => m.id === pick) ? pick : "A") : view === "B" ? "B" : "A";
  const choose = (id: string) => { setPick(id); localStorageSet("panelWorld", id); };
  const setTab = (t: Tab) => { set({ tab: tab === t ? null : t }); localStorageSet("tab", t === tab ? "" : (t as string)); };
  return (
    <>
      <nav className="rail">
        {([["progress", "🧭", "Progress"], ["why", "🐢", "Why slow?"], ["chronicle", "📖", "Chronicle"], ["people", "👥", "People"], ["knowledge", "✦", "Knowledge"], ["stats", "📈", "Stats"]] as const).map(([t, i, l]) => (
          <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)} title={l}><span>{i}</span><small>{l}</small></button>
        ))}
      </nav>
      {tab && (
        <section className="panel">
          {view === "split" && metas.length > 1 && (tab === "chronicle" || tab === "people") && (
            <div className="seg panel-world">
              {metas.map((m) => (
                <button key={m.id} className={primary === m.id ? "on" : ""} onClick={() => choose(m.id)}><span className={`dot ${m.culture}`} />{m.name}</button>
              ))}
            </div>
          )}
          {tab === "progress" && metas.map((m) => (view === "split" || m.id === primary) && <Progress key={m.id} world={m.id} name={m.name} />)}
          {tab === "why" && <Why metas={metas} />}
          {tab === "chronicle" && <Chronicle world={primary} />}
          {tab === "people" && <People world={primary} />}
          {tab === "knowledge" && <Knowledge metas={metas} />}
          {tab === "stats" && <StatsPanel metas={metas} />}
        </section>
      )}
    </>
  );
}

type Rung = { name: string; needs: string; reached: boolean; by: string; day: number | null };
type Project = {
  id: string; kind: "build" | "discover" | "make" | "find"; key: string; title: string; why: string; chosen_by: string; by: string;
  since_day: number; status: string; progress: number; helpers: number; attempts: number;
};
type RoadStep = { kind: string; key: string; name: string; done: boolean; needs: string };
type ProgressData = {
  project?: { active: Project | null; done: { id: string; day: number; text: string }[] };
  road?: { age: string; steps: RoadStep[]; text: string } | null;
  research?: { insight: number; next_idea: number; hints: { text: string; day: number; by: string; found: boolean }[] };
  famous?: { name: string; renown: number } | null;
  food_days?: number | null;
  at_risk?: { what: string; keeper: string; old: boolean; age: number; lifespan: number }[];
  day: number; era: { index: number; name: string; of: number }; next: Rung | null; ladder: Rung[];
  doing: [string, number][]; aims: [string, number][]; recent: { day: number; lines: string[] }[];
  counts: { population: number; discoveries: number; structures: number; beliefs: number; known: number };
};

/** 🧭 Is this world getting anywhere? Its place on the road to space, what everyone is doing now, and how the
 *  latest achievements happened, in plain words. */
function Progress({ world, name }: { world: string; name: string }) {
  const p = usePoll(() => api<ProgressData>(`/api/worlds/${world}/progress`), 8000, [world]);
  const brain = useUI((s) => s.brains[world]?.label);
  if (!p) return <p className="muted">Loading…</p>;
  const pct = Math.round((p.era.index / p.era.of) * 100);
  const plain = (s: string) => s.replace(/\*\*(.+?)\*\*/g, "$1").replace(/\*(.+?)\*/g, "$1").replace(/ ?\(#\d+\)/g, "");
  return (
    <div className="progress">
      <div className="panel-head"><h3>{name}</h3><small className="muted">{brain || "instinct"} · day {p.day}</small></div>
      <div className="prog-era">
        <b>{p.era.name}</b> <small className="muted">age {p.era.index + 1} of {p.era.of + 1} on the road to space</small>
        <div className="prog-bar"><span style={{ width: `${Math.max(3, pct)}%` }} /></div>
        {p.next
          ? <small>Next: <b>{p.next.name}</b>, when someone works out how to make a <b>{p.next.needs}</b>.</small>
          : <small>🚀 They reached space!</small>}
        {p.road && p.road.steps.length > 0 && (
          <div className="prog-road" title="Everything still between this village and its next age, in order; ✗ marks what's missing">
            <small className="muted">Road to the {p.road.age}: </small>
            {p.road.steps.map((s, i) => (
              <small key={s.kind + s.key} className={s.done ? "on" : "off"}>
                {i > 0 && " · "}{s.name} {s.done ? "✓" : "✗"}{s.needs && <span className="muted"> ({s.needs})</span>}
              </small>
            ))}
          </div>
        )}
      </div>
      <div className="prog-ladder">
        {p.ladder.map((r) => (
          <span key={r.name} className={r.reached ? "on" : ""} title={r.reached && r.by ? `${r.name}: ${r.by} made the first ${r.needs} on day ${r.day}` : r.needs ? `${r.name}: needs a ${r.needs}` : r.name}>
            {r.reached ? "✔" : "○"} {r.name}
          </span>
        ))}
      </div>
      <div className="prog-row"><small className="muted">
        👥 {p.counts.population} chits · ✦ {p.counts.discoveries} discoveries · 🏠 {p.counts.structures} buildings · 🕯 {p.counts.beliefs} beliefs
        {p.food_days != null && <> · <span className={p.food_days < 3 ? "food-low" : ""} title="How long the food in the stores would feed the village; below 3 days, chits put the project aside and fill the stores">🍞 {p.food_days} days of food in store</span></>}
      </small></div>
      <VillageProject p={p} plain={plain} />
      {p.at_risk && p.at_risk.length > 0 && (
        <div className="prog-risk" title="Things only one living chit knows how to make: if it dies without passing them on, the village forgets them">
          <h4>⏳ Knowledge at risk</h4>
          <ul className="prog-list">{p.at_risk.map((r) => (
            <li key={r.what} className={r.old ? "food-low" : ""}>{r.what}: only {r.keeper} knows{r.old ? ` (old: ${r.age} of ~${r.lifespan} days)` : ""}</li>
          ))}</ul>
        </div>
      )}
      <h4>Right now</h4>
      <p className="small">{p.doing.map(([what, n]) => `${n} ${what}`).join(" · ") || "nobody around"}</p>
      {p.aims.length > 0 && (<>
        <h4>Working towards</h4>
        <ul className="prog-list">{p.aims.map(([aim, n]) => <li key={aim}>{n > 1 && <b>{n}× </b>}{aim}</li>)}</ul>
      </>)}
      {p.recent.map((r) => (
        <div key={r.day}>
          <h4>{r.day === p.day ? "Today" : "Yesterday"}: how they did it</h4>
          <ul className="prog-list">{r.lines.map((l, i) => <li key={i}>{plain(l)}</li>)}</ul>
        </div>
      ))}
      {!p.recent.length && <p className="small muted">Nothing new learned or built in the last two days yet.</p>}
    </div>
  );
}

/** 🏗 The one thing the whole village is working towards now, its scholars' ideas, and who everyone looks up to. */
function VillageProject({ p, plain }: { p: ProgressData; plain: (s: string) => string }) {
  const cur = p.project?.active;
  const done = p.project?.done ?? [];
  const hints = p.research?.hints ?? [];
  if (!cur && !done.length && !hints.length && !p.famous) return null;
  const call = cur && (cur.chosen_by === "need" ? "chosen by need" : `${cur.chosen_by} ${cur.by}'s call`);
  return (
    <div className="prog-project">
      <h4>🏗 Village project</h4>
      {cur ? (<>
        <b>{cur.title.charAt(0).toUpperCase() + cur.title.slice(1)}</b> <small className="muted">{call} · since day {cur.since_day}</small>
        <div className="prog-bar" title={`${Math.round(cur.progress * 100)}%`}><span style={{ width: `${Math.max(3, Math.round(cur.progress * 100))}%` }} /></div>
        <small>{cur.status} · {cur.helpers} helping <span className="muted">({cur.why})</span></small>
      </>) : <p className="small muted">No project right now.</p>}
      {done.length > 0 && <ul className="prog-list">{done.slice(0, 3).map((d) => <li key={d.id}>day {d.day}: {plain(d.text)}</li>)}</ul>}
      {hints.length > 0 && (<>
        <h4>📚 Scholars' ideas <small className="muted">{p.research!.insight}/{p.research!.next_idea} insight to the next</small></h4>
        <ul className="prog-list">{hints.map((h, i) => <li key={i} className={h.found ? "muted" : ""}>day {h.day}{h.by ? ` (${h.by})` : ""}: {h.text}{h.found ? " ✔ came true" : ""}</li>)}</ul>
      </>)}
      {p.famous && <p className="small">⭐ Most renowned: <b>{p.famous.name}</b> <span className="muted">(renown {p.famous.renown}; chits near them follow their lead)</span></p>}
    </div>
  );
}

/** 🐢 Why is nothing happening? The biggest reasons each world is slow, in plain words, from the game's own
 *  diagnostics (the same numbers as /api/diagnostics). */
function Why({ metas }: { metas: { id: string; name: string; culture: string }[] }) {
  const d = usePoll(() => api<WhyData>("/api/why"), 15000, []);
  if (!d) return <p className="muted">Loading…</p>;
  return (
    <div className="why">
      <div className="panel-head"><h3>Why is nothing happening?</h3></div>
      <p className="muted small explain">The biggest things slowing each world down. Counts run since the game server last started.</p>
      {metas.map((m) => {
        const lines = whyLines(d, m.id);
        return (
          <div key={m.id} className="why-world">
            <h4><span className={`dot ${m.culture}`} />{m.name}</h4>
            {lines.length
              ? <ol className="why-list">{lines.map((l, i) => <li key={i} className={`why-${l.kind}`}>{l.text}</li>)}</ol>
              : <p className="small muted">{WHY_NOTHING}</p>}
          </div>
        );
      })}
      <p className="small"><a href={authedUrl("/api/diagnostics.txt")} target="_blank" rel="noreferrer">Open the full diagnostics</a></p>
    </div>
  );
}

function goTo(world: string, e: WorldEvent) {
  const ui = useUI.getState();
  if (e.x != null && e.y != null) ui.set({ focus: { world, x: e.x + 0.5, y: e.y + 0.5, t: Date.now() } });
  if (e.actor && worlds[world]?.agents.has(e.actor)) ui.set({ selected: { world, id: e.actor } });
  if (ui.view !== "split" && ui.view !== world) ui.set({ view: world as any });
}

function Chronicle({ world }: { world: string }) {
  useUI((s) => s.tick);
  const [mode, setMode] = useState<"live" | "days" | "weeks">("live");
  const [saga, setSaga] = useState<string>("");
  const [thread, setThread] = useState<string[] | null>(null);
  const [story, setStory] = useState<any>(null);
  useEffect(() => {
    if (thread && thread.length === 0) api("/api/story/x?since_day=1&max_posts=6").then((r) => setThread(r.posts)).catch(() => setThread(null));
  }, [thread]);
  const weeks = usePoll(() => (mode === "weeks" ? api<any[]>(`/api/worlds/${world}/sagas`) : Promise.resolve(null)), 15000, [world, mode]);
  const [min, setMin] = useState(2);
  const days = usePoll(() => (mode === "days" ? api(`/api/worlds/${world}/chronicle`) : Promise.resolve(null)), 8000, [world, mode]);
  const evs = (worlds[world]?.events || []).filter((e) => e.importance >= min).slice(-120).reverse();
  return (
    <div className="chron">
      <div className="panel-head">
        <h3>Chronicle <small className="muted">{world === "A" ? "World A" : "World B"}</small></h3>
        <div className="seg small">
          <button className={mode === "live" ? "on" : ""} onClick={() => setMode("live")}>Live</button>
          <button className={mode === "days" ? "on" : ""} onClick={() => setMode("days")}>By day</button>
          <button className={mode === "weeks" ? "on" : ""} onClick={() => setMode("weeks")}>Weeks</button>
          <button onClick={() => api(`/api/worlds/${world}/recap`).then(setStory).catch(() => {})} title="The story so far, for someone who has just arrived">📜 So far</button>
          <button onClick={() => setThread([])} title="A ready-to-post X thread built from real moments">𝕏 Thread</button>
          <a className="log-link" href={authedUrl(`/api/worlds/${world}/log.txt`)} target="_blank" rel="noreferrer" title="Everything that happened in this world, as a text log">⬇ log</a>
        </div>
      </div>
      {mode === "live" && (
        <>
          <div className="seg small filters">
            {[[1, "All"], [2, "Notable"], [4, "Big moments"]].map(([v, l]) => <button key={v} className={min === v ? "on" : ""} onClick={() => setMin(v as number)}>{l}</button>)}
          </div>
          <ul className="feed">
            {evs.map((e) => (
              <li key={e.seq} className={`k-${e.kind} imp${e.importance}`} onClick={() => goTo(world, e)}>
                <span className="ico">{KIND_ICON[e.kind] ?? "·"}</span>
                <div><p>{e.text}</p><small>day {Math.floor(e.tick / 240) + 1} · {String(Math.floor((e.tick % 240) / 10)).padStart(2, "0")}:00</small></div>
              </li>
            ))}
            {!evs.length && <li className="muted">Nothing yet. The chits are just waking up…</li>}
          </ul>
        </>
      )}
      {story && (
        <div className="modal-bg" onClick={() => setStory(null)}>
          <div className="modal thread" onClick={(e) => e.stopPropagation()}>
            <button className="x" onClick={() => setStory(null)}>✕</button>
            <h2>📜 {story.title}</h2>
            <ul className="recap">{story.lines.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul>
            <div className="row"><button onClick={() => navigator.clipboard?.writeText(story.lines.join("\n"))}>Copy</button></div>
          </div>
        </div>
      )}
      {thread && (
        <div className="modal-bg" onClick={() => setThread(null)}>
          <div className="modal thread" onClick={(e) => e.stopPropagation()}>
            <button className="x" onClick={() => setThread(null)}>✕</button>
            <h2>𝕏 Thread</h2>
            <img className="card-img" src={authedUrl(`/api/story/card.svg?t=${Date.now() >> 14}`)} alt="scoreboard card" />
            <p className="row"><a href={authedUrl("/api/story/card.svg")} download="little-chits-card.svg">⬇ Download card (SVG)</a>
              <a href={authedUrl("/api/story/card.png")} download="little-chits-card.png">⬇ PNG</a></p>
            {thread.length === 0 && <p className="muted">Writing it from today's moments…</p>}
            {thread.map((p, i) => (
              <div key={i} className="post">
                <p>{p}</p>
                <div className="row"><small className="muted">{i + 1}/{thread.length} · {p.length}/280</small>
                  <button onClick={() => navigator.clipboard?.writeText(p)}>Copy</button></div>
              </div>
            ))}
          </div>
        </div>
      )}
      {mode === "weeks" && (
        <div className="days">
          {(weeks ?? []).length === 0 && <p className="muted">The first weekly saga is written at the end of day 7.</p>}
          {(weeks ?? []).map((w: any) => (
            <button key={w.week} className="saga-btn" onClick={() => api(`/api/worlds/${world}/sagas/${w.week}`).then((r) => setSaga(r.markdown))}>Week {w.week}</button>
          ))}
          {saga && <pre className="saga">{saga}</pre>}
        </div>
      )}
      {mode === "days" && (
        <div className="days">
          {(days as any[] | null)?.map((d) => (
            <article key={d.day} className="day">
              <h4>Day {d.day}</h4>
              <p className="summary">{d.summary}</p>
              <ul>{d.highlights.map((e: WorldEvent) => <li key={e.seq} onClick={() => goTo(world, e)}><span className="ico">{KIND_ICON[e.kind] ?? "·"}</span>{e.text}</li>)}</ul>
            </article>
          )) ?? <p className="muted">Loading…</p>}
        </div>
      )}
    </div>
  );
}

function Hall({ world }: { world: string }) {
  const list = usePoll(() => api<any[]>(`/api/worlds/${world}/hall?limit=80`), 15000, [world]);
  if (!list) return <small className="muted">Remembering…</small>;
  if (!list.length) return <small className="muted">No one has left a mark worth a biography yet.</small>;
  return (
    <ul className="hall">
      {list.map((b) => (
        <li key={b.id}>
          <Portrait hue={b.hue} child={false} size={30} />
          <div><b>{b.name}</b> <small className="muted">day {b.born_day}–{b.died_day} · g{b.generation}</small><p>{b.text}</p></div>
        </li>
      ))}
    </ul>
  );
}

function People({ world }: { world: string }) {
  const [dead, setDead] = useState(false);
  const [hall, setHall] = useState(false);
  const list = usePoll(() => api<any[]>(`/api/worlds/${world}/agents?dead=${dead}`), 2500, [world, dead]);
  const selected = useUI((s) => s.selected);
  const sorted = useMemo(() => (list || []).slice().sort((a, b) => (b.alive - a.alive) || ((b.leader ? 1 : 0) - (a.leader ? 1 : 0)) || b.known - a.known), [list]);
  return (
    <div>
      <div className="panel-head">
        <h3>People <small className="muted">{list ? list.filter((a) => a.alive).length : "…"} alive</small></h3>
        <label className="toggle"><input type="checkbox" checked={dead} onChange={(e) => setDead(e.target.checked)} /> show departed</label>
        <label className="toggle" title="A short biography for every chit that mattered"><input type="checkbox" checked={hall} onChange={(e) => setHall(e.target.checked)} /> 🏛 hall</label>
      </div>
      {hall ? <Hall world={world} /> : <ul className="people">
        {sorted.map((a) => (
          <li key={a.id} className={`${selected?.id === a.id ? "sel" : ""} ${a.alive ? "" : "gone"}`}
            onClick={() => {
              const live = worlds[world]?.agents.get(a.id);
              useUI.getState().set({ selected: { world, id: a.id }, follow: !!live, focus: live ? { world, x: live.x + 0.5, y: live.y + 0.5, t: Date.now() } : null });
            }}>
            <Portrait hue={a.hue} child={a.child} size={34} tool={a.tool} />
            <div>
              <b>{a.leader && <span title="the leader">👑 </span>}{a.name}</b> {a.job
                ? <span className={`role job`} title={`Job (${a.job_source === "chosen" ? "chosen by its mind" : "from practice"}) · role from behaviour: ${a.role}`}>{a.job}{a.job_source === "chosen" ? " ✋" : ""}</span>
                : <span className={`role r-${a.role}`} title="Role, inferred from what this chit does">{a.role}</span>}{a.think && <span title="thinking"> 💭</span>}
              <small>{a.alive ? (a.goal || a.act) : `† ${a.cause}`}</small>
            </div>
            <span className="meta">✦{a.known}<br /><small>{a.age}d · g{a.generation}</small></span>
          </li>
        ))}
      </ul>}
    </div>
  );
}

function ComparePanel() {
  const d = usePoll(() => api<{ compare: any; markdown: string; tweet: string }>("/api/compare"), 8000, []);
  const [copied, setCopied] = useState("");
  if (!d) return <div className="compare"><small className="muted">Comparing…</small></div>;
  const c = d.compare;
  const copy = (what: string, text: string) => { navigator.clipboard?.writeText(text); setCopied(what); setTimeout(() => setCopied(""), 1500); };
  return (
    <div className="compare">
      <b>{c.headline}</b>
      <div className="compare-score"><span>{c.divergence}</span>/100 divergent
        <small className="muted"> · knowledge {c.scores.knowledge.toFixed(2)} · order {c.scores.order.toFixed(2)} · culture {c.scores.culture.toFixed(2)}</small></div>
      <div className="compare-cols">
        {Object.values(c.worlds).map((w: any) => (
          <div key={w.id}>
            <h4>Only in {w.name}</h4>
            {(c.only_names?.[w.id] || c.only[w.id]).length
              ? <ul>{(c.only_names?.[w.id] || c.only[w.id]).map((n: string) => <li key={n}>{n}</li>)}</ul>
              : <small className="muted">nothing yet</small>}
          </div>
        ))}
      </div>
      <div className="row">
        <button onClick={() => copy("md", d.markdown)}>{copied === "md" ? "Copied ✓" : "Copy markdown"}</button>
        <button onClick={() => copy("tw", d.tweet)}>{copied === "tw" ? "Copied ✓" : "Copy tweet"}</button>
      </div>
    </div>
  );
}

type SpreadNode = { id: string; name: string; alive: boolean; how: string; day: number; worked: boolean; passed_to: SpreadNode[]; more: number };
const HOW: Record<string, string> = { discovered: "found it", insight: "had the idea", taught: "was taught", observed: "watched",
  read: "read it", raised: "grew up with it", inspected: "worked it out", built: "built it", instinct: "always knew" };

/** 🌳 How a village came to know a thing: from whoever found it, who passed it to whom, and how. */
function SpreadTree({ world, name, k }: { world: string; name: string; k: string }) {
  const t = usePoll(() => api<{ name: string; knowers: number; alive: number; roots: SpreadNode[] }>(`/api/worlds/${world}/spread/${encodeURIComponent(k)}`), 8000, [world, k]);
  if (!t) return null;
  const Node = ({ n }: { n: SpreadNode }) => (
    <li><span className={n.alive ? "" : "dead"}>{n.alive ? "" : "† "}{n.name}</span> <small className="muted">{HOW[n.how] ?? n.how} · day {n.day}{n.worked ? " · made it" : ""}</small>
      {n.passed_to.length > 0 && <ul>{n.passed_to.map((c) => <Node key={c.id} n={c} />)}</ul>}
      {n.more > 0 && <small className="muted"> …and {n.more} more</small>}
    </li>
  );
  return (
    <div className="spread-world"><h4>🌳 {t.name} in {name} <small className="muted">{t.alive} of {t.knowers} who knew it are alive</small></h4>
      {t.roots.length ? <ul>{t.roots.map((n) => <Node key={n.id} n={n} />)}</ul> : <p className="muted small">Nobody there knows it.</p>}
    </div>
  );
}

function Knowledge({ metas }: { metas: { id: string; name: string; culture: string }[] }) {
  const rows = usePoll(() => api<any[]>("/api/knowledge"), 3000, []);
  const inv = usePoll(() => api<Record<string, any[]>>("/api/inventions"), 5000, []);
  const bel = usePoll(() => api<Record<string, any[]>>("/api/beliefs"), 5000, []);
  const [cmpOpen, setCmpOpen] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);
  if (!rows) return <p className="muted">Loading…</p>;
  const shown = rows.filter((r) => r.discovered);
  const hidden = rows.length - shown.length;
  return (
    <div>
      <div className="panel-head"><h3>Knowledge</h3><small className="muted">{shown.length} known · {hidden} undiscovered</small>
        {metas.length >= 2 && <button className="compare-btn" onClick={() => setCmpOpen(!cmpOpen)} title="How differently did the two worlds think?">⚖ Compare</button>}</div>
      {cmpOpen && <ComparePanel />}
      <p className="muted small explain">Who discovered what first, and how far it has spread. {metas.every((m) => m.culture === "direct")
        ? "Every world here can talk, teach and write."
        : metas.map((m) => `${m.name} ${m.culture === "direct" ? "can teach and write" : "can only watch and study what others leave behind"}`).join("; ") + "."}</p>
      <table className="know">
        <thead><tr><th></th>{metas.map((m) => <th key={m.id}><span className={`dot ${m.culture}`} />{m.name}</th>)}</tr></thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.key}>
              <td><b className="spread-open" title="How did they come to know it?" onClick={() => setOpenKey(openKey === r.key ? null : r.key)}>{r.icon} {r.name}</b><small className="muted"> {r.kind === "design" ? "build" : "make"}</small></td>
              {metas.map((m) => {
                const w = r.worlds[m.id];
                const pct = w.population ? (w.knowers / w.population) * 100 : 0;
                return (
                  <td key={m.id}>
                    {w.first_by || w.knowers ? (
                      <>
                        <div className="track"><i style={{ width: `${pct}%` }} className={m.culture} /></div>
                        <small title="know how / have actually made it / population">{w.knowers}{w.worked !== undefined && w.worked !== w.knowers ? ` (${w.worked} made it)` : ""}/{w.population}{w.first_by && !r.starting ? ` · ${w.first_by} d${w.first_day}` : ""}</small>
                        {w.local_name && <small className="local-name" title="what this world calls it">“{w.local_name}”</small>}
                      </>
                    ) : <small className="muted">—</small>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {openKey && <div className="spread">{metas.map((m) => <SpreadTree key={m.id} world={m.id} name={m.name} k={openKey} />)}</div>}
      <div className="panel-head inv-head"><h3>💡 Inventions</h3><small className="muted">things only one world thought of</small></div>
      {metas.map((m) => {
        const list = inv?.[m.id] || [];
        return (
          <div key={m.id} className="inv-world">
            <h4><span className={`dot ${m.culture}`} />{m.name}</h4>
            {list.length ? list.map((x) => (
              <div key={x.key} className="inv-row">
                <b>💡 {x.name}</b> <small className="muted">for {x.purpose}</small>
                <small className="muted"> · {x.by_name}, day {x.day} · {x.knowers} know it</small>
                {x.purpose_text && <div className="small muted">“{x.purpose_text}”</div>}
              </div>
            )) : <small className="muted">nothing invented yet</small>}
          </div>
        );
      })}
      <div className="panel-head inv-head"><h3>🕯 Beliefs</h3><small className="muted">what the chits believe (not what is true)</small></div>
      {metas.map((m) => {
        const list = bel?.[m.id] || [];
        return (
          <div key={m.id} className="inv-world">
            <h4><span className={`dot ${m.culture}`} />{m.name}</h4>
            {list.length ? list.map((b) => (
              <div key={b.id} className="inv-row">
                <b>🕯 {b.name}</b> <small className="muted">· founded by {b.founder_name}, day {b.day} · {b.count} follower{b.count === 1 ? "" : "s"}
                  {b.shrines ? ` · ${b.shrines} shrine${b.shrines > 1 ? "s" : ""}` : ""}{b.scripture ? " · 📜 has a scripture" : b.tablets ? ` · ${b.tablets} tablet${b.tablets > 1 ? "s" : ""}` : ""}</small>
                <div className="small muted">“{b.tenet}”</div>
              </div>
            )) : <small className="muted">no beliefs yet</small>}
          </div>
        );
      })}
    </div>
  );
}

function Spark({ series, colors, label }: { series: number[][]; colors: string[]; label: string }) {
  const W = 260, H = 54;
  const max = Math.max(1, ...series.flat());
  const n = Math.max(2, ...series.map((s) => s.length));
  return (
    <div className="spark">
      <div className="spark-head"><span>{label}</span>{series.map((s, i) => <b key={i} style={{ color: colors[i] }}>{s[s.length - 1] ?? 0}</b>)}</div>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        {series.map((s, i) => (
          <polyline key={i} fill="none" stroke={colors[i]} strokeWidth={2} strokeLinejoin="round"
            points={s.map((v, j) => `${(j / (n - 1)) * W},${H - 3 - (v / max) * (H - 8)}`).join(" ")} />
        ))}
      </svg>
    </div>
  );
}

function Rivals() {
  const r = usePoll(() => api<any>("/api/rivals"), 6000, []);
  if (!r || !r.contact) return null;
  const ids = Object.keys(r.table);
  const state = (id: string) => { const rel = r.relations[id] || {}; const o = Object.values(rel)[0] as any; return o?.met ? o.state : "not met yet"; };
  const icon: Record<string, string> = { war: "⚔️", peace: "🕊️", tension: "😠", "not met yet": "🌊", unknown: "🌊" };
  return (
    <div className="rivals">
      <h4>⚔🏝 The islands {ids.length === 2 && <>{icon[state(ids[0])] || ""} <small className="muted">{state(ids[0])}</small></>}</h4>
      <table className="know"><thead><tr><th></th>{ids.map((i) => <th key={i}>{r.table[i].name}</th>)}</tr></thead>
        <tbody>{["population", "discoveries", "structures", "trades", "raids", "gifts"].map((k) => (
          <tr key={k}><td>{k}</td>{ids.map((i) => <td key={i}>{r.table[i][k]}</td>)}</tr>))}</tbody></table>
      <small><a href="/api/rivals/card.svg" target="_blank">🖼 rivals card</a></small>
    </div>
  );
}

function Government({ metas }: { metas: { id: string; name: string }[] }) {
  const g = usePoll(() => api<Record<string, any>>("/api/government"), 6000, []);
  if (!g) return null;
  return (
    <div className="gov">
      {metas.map((m) => {
        const x = g[m.id];
        if (!x) return null;
        return (
          <div key={m.id}>
            <b>👑 {m.name}:</b> {x.leader ? <>{x.leader} <small className="muted">({x.title}{x.since_day ? ` since day ${x.since_day}` : ""})</small></> : <small className="muted">no {x.title} yet</small>}
            {x.laws.length > 0 && <ul>{x.laws.map((l: any) => <li key={l.id}>“{l.text}” <small className="muted">— {l.by_name}, day {Math.floor(l.tick / 240) + 1}</small></li>)}</ul>}
          </div>
        );
      })}
    </div>
  );
}

type ScoreRow = {
  world: string; name: string; label: string; model: string | null; day: number; era_name: string; population: number;
  discoveries: number; discoveries_this_session: number; decisions: number; discoveries_per_100_decisions: number | null;
  model_share_pct: number | null; step_success_pct: number; escalation_pct: number | null; latency_p50_ms: number | null;
  projects_done: number;
};

/** 🏁 Which model is building the better civilisation: the two worlds side by side, the leader on each line marked. */
/** 🔀 What if: a copy of a world as it is now, stepping alongside it on instinct (or unable to talk), to watch the two
 *  drift apart. Kept until the game restarts. */
function Forks({ metas }: { metas: { id: string; name: string }[] }) {
  const [n, setN] = useState(0);
  const [err, setErr] = useState("");
  const list = usePoll(() => api<any[]>("/api/forks"), 5000, [n]);
  const make = (wid: string, culture?: string) =>
    api(`/api/worlds/${wid}/fork`, { brain: "instinct", ...(culture ? { culture } : {}) }).then(() => { setErr(""); setN(n + 1); }).catch((e) => setErr(String(e)));
  const end = (fid: string) => api(`/api/forks/${encodeURIComponent(fid)}`, undefined, "DELETE").then(() => setN(n + 1)).catch((e) => setErr(String(e)));
  return (
    <div className="forks">
      <h4>🔀 What if…</h4>
      <p className="muted small">A copy of a world as it is now, run alongside it on instinct (no model is asked), or unable to talk. Watch how far the two drift apart.</p>
      <div className="row">{metas.map((m) => (
        <span key={m.id}>
          <button onClick={() => make(m.id)} title={`Copy ${m.name} now and run the copy on instinct`}>{m.name} on instinct</button>
          <button onClick={() => make(m.id, "stigmergy")} title={`Copy ${m.name} now, and its chits can no longer talk, teach or write`}>{m.name}, silent</button>
        </span>
      ))}</div>
      {err && <p className="err small">{err}</p>}
      {(list || []).map((f) => (
        <div key={f.id} className="fork">
          <b>{f.name}</b> <small className="muted">from day {f.from_day} · {f.brain}{f.culture === "stigmergy" ? " · can't talk" : ""}</small>
          <button className="x" onClick={() => end(f.id)} title="End this what-if">✕</button>
          <table><tbody>
            <tr><td></td><td>what if</td><td>real</td></tr>
            {(["population", "discoveries", "known", "deaths", "era"] as const).map((k) => <tr key={k}><td className="muted">{k}</td><td>{f.fork[k]}</td><td>{f.original[k]}</td></tr>)}
          </tbody></table>
          {f.only_fork_knows.length > 0 && <small>Only the what-if knows: {f.only_fork_knows.join(", ")}</small>}
          {f.only_original_knows.length > 0 && <small><br />Only the real world knows: {f.only_original_knows.join(", ")}</small>}
        </div>
      ))}
    </div>
  );
}

function Scorecard() {
  const sc = usePoll(() => api<{ rows: ScoreRow[]; lead: Record<string, string>; controlled: boolean; warning: string; note: string }>("/api/scorecard"), 10000, []);
  if (!sc || sc.rows.length < 1) return null;
  const lines: [string, string, (r: ScoreRow) => string][] = [
    ["Model", "", (r) => r.model || r.label],
    ["Age", "era", (r) => r.era_name],
    ["Discoveries", "discoveries", (r) => `${r.discoveries}`],
    ["Chits", "population", (r) => `${r.population}`],
    ["Discoveries / 100 decisions", "discoveries_per_100_decisions", (r) => r.discoveries_per_100_decisions == null ? "—" : `${r.discoveries_per_100_decisions}`],
    ["Plans from the model", "model_share_pct", (r) => r.model_share_pct == null ? "—" : `${r.model_share_pct}%`],
    ["Steps that worked", "step_success_pct", (r) => `${r.step_success_pct}%`],
    ["Asked for its own idea", "", (r) => r.escalation_pct == null ? "—" : `${r.escalation_pct}%`],
    ["Time per decision (median)", "latency_p50_ms", (r) => r.latency_p50_ms ? `${(r.latency_p50_ms / 1000).toFixed(1)} s` : "—"],
    ["Village projects done", "projects_done", (r) => `${r.projects_done}`],
  ];
  return (
    <div className="scorecard">
      <h4>🏁 Scorecard</h4>
      {sc.warning && <p className="small"><b>⚠ {sc.warning}</b></p>}
      <table>
        <thead><tr><th /><>{sc.rows.map((r) => <th key={r.world}>{r.name}</th>)}</></tr></thead>
        <tbody>{lines.map(([label, key, f]) => (
          <tr key={label}><td className="muted">{label}</td>{sc.rows.map((r) => (
            <td key={r.world} className={key && sc.lead[key] === r.world ? "lead" : ""}>{f(r)}</td>
          ))}</tr>
        ))}</tbody>
      </table>
      <small className="muted">{sc.note}</small>
    </div>
  );
}

function StatsPanel({ metas }: { metas: { id: string; name: string; culture: string }[] }) {
  const hist = usePoll(() => Promise.all(metas.map((m) => api<Stats[]>(`/api/worlds/${m.id}/history`))), 10000, [metas.length]);
  useUI((s) => s.tick);
  if (!hist) return <p className="muted">Loading…</p>;
  const colors = metas.map((m) => (m.culture === "direct" ? "#ffb86b" : "#7dd3fc"));
  const series = (f: (s: Stats) => number) => hist.map((h, i) => {
    const live = worlds[metas[i].id]?.stats;
    const arr = h.map(f);
    if (live) arr.push(f(live));
    return arr;
  });
  return (
    <div>
      <div className="panel-head"><h3>Stats</h3><small className="muted">{metas.map((m, i) => <span key={m.id} style={{ color: colors[i] }}> ● {m.name}</span>)}</small></div>
      <div className="eras">{metas.map((m, i) => (
        <div key={m.id}><span style={{ color: colors[i] }}>● {m.name}</span> <b>{worlds[m.id]?.stats?.era ?? worlds[m.id]?.clock?.era ?? "Wanderers"}</b></div>
      ))}</div>
      <div className="eras">{metas.map((m, i) => {
        const jobs = (worlds[m.id]?.stats as any)?.jobs || {};
        const txt = Object.entries(jobs).sort((x: any, y: any) => y[1] - x[1]).map(([j, n]) => `${n} ${j}${(n as number) > 1 ? "s" : ""}`).join(" · ");
        const st = worlds[m.id]?.stats as any;
        return <div key={m.id}><span style={{ color: colors[i] }}>● jobs</span> <small className="muted">{txt || "none yet"}</small>
          <div><small className="muted">🤝 {st?.trades ?? 0} trades today{st?.currency ? ` · 🪙 money: ${st.currency.replace(/_/g, " ")}` : " · no money yet"}</small></div></div>;
      })}</div>
      <Scorecard />
      <Forks metas={metas} />
      <Rivals />
      <Government metas={metas} />
      <p className="small"><a href={authedUrl("/api/replay/export?days=7")} download>⬇ Download a replay of the last 7 days</a>
        <small className="muted"> (a single file: open it in <a href="/replay.html" target="_blank">the replay viewer</a>, no server needed)</small></p>
      <Spark label="Population" series={series((s) => s.population)} colors={colors} />
      <Spark label="Discoveries" series={series((s) => s.discoveries)} colors={colors} />
      <Spark label="Things known (sum)" series={series((s) => s.knowledge)} colors={colors} />
      <Spark label="Buildings" series={series((s) => s.structures)} colors={colors} />
      <Spark label="Goods stored" series={series((s) => s.stored)} colors={colors} />
      <Spark label="Generations" series={series((s) => s.generations)} colors={colors} />
    </div>
  );
}
