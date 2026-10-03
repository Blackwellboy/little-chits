import { useShallow } from "zustand/react/shallow";
import { useEffect, useRef, useState } from "react";
import { api, errorText } from "../net/socket";
import { notifyError, useUI } from "../state/store";
import { SKIP_CHOICES, SKIP_NOTE, skipProgress, skipResult } from "./skip";

/** ⏩ Skip ahead (play games): run at full speed to the next discovery, the next big moment or N days. */
export function SkipControl() {
  const { control, set } = useUI(useShallow((s) => ({ control: s.control, set: s.set })));
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const seen = useRef<number | null>(null);
  const ended = control?.last_skip?.ended ?? 0;
  useEffect(() => {  // say how a skip ended for a few seconds (not one that was over before this page opened)
    if (!control) return;
    if (seen.current === null) { seen.current = ended; return; }
    if (ended === seen.current) return;
    seen.current = ended;
    setNote(skipResult(control.last_skip));
    const t = setTimeout(() => setNote(""), 12000);
    return () => clearTimeout(t);
  }, [ended, !control]);
  const send = (path: string, body: object) =>
    api(path, body).then((c) => set({ control: c })).catch((e) => notifyError(errorText(e)));
  if (control?.skip) {
    return (
      <span className="skip-run" title={SKIP_NOTE}>
        <b>{skipProgress(control.skip)}</b>
        <small>mostly instinct-driven</small>
        <button onClick={() => send("/api/skip/stop", {})}>Stop</button>
      </span>
    );
  }
  return (
    <span className="skip-wrap">
      <button className={`pace-btn ${open ? "on" : ""}`} title={`Skip ahead at full speed, then go back to this speed. ${SKIP_NOTE}`}
        onClick={() => setOpen(!open)}>⏩ skip</button>
      {note && !open && <span className="skip-note">{note}</span>}
      {open && (
        <div className="skip-menu">
          {SKIP_CHOICES.map((ch) => (
            <button key={ch.label} onClick={() => { setOpen(false); setNote(""); send("/api/skip", { until: ch.until, days: ch.days }); }}>{ch.label}</button>
          ))}
          <small className="muted">{SKIP_NOTE}</small>
        </div>
      )}
    </span>
  );
}
