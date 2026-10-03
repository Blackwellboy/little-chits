/** Which milestone fills the screen, and for how long. Pure of React, so the timing can be tested. */
import { milestoneOf, type Toast } from "../state/milestones";

export type Shown = { key: string; kind: string; text: string; world: string; label: string; icon: string };

/** Shows each banner-worthy toast once and takes it down after a few seconds. The banner's timer is its own: an
 *  ordinary toast arriving while a banner is up used to cancel it (the effect that set it was cleaned up, and
 *  with no new banner nothing set another), and the banner stayed until it was clicked. */
export function bannerDriver(show: (s: Shown | null) => void) {
  const seen = new Set<string>();
  let timer: ReturnType<typeof setTimeout> | null = null;
  const stop = () => { if (timer != null) clearTimeout(timer); timer = null; };
  return {
    update(toasts: Toast[]) {
      const t = toasts.find((x) => (milestoneOf(x)?.banner || x.kind === "storyteller") && !seen.has(x.key));
      if (!t) return;  // (nothing new to show: the banner that is up keeps its time)
      seen.add(t.key);
      const ms = milestoneOf(t);
      show({ key: t.key, kind: t.kind, text: t.text, world: t.world, label: ms?.label ?? "news", icon: ms?.icon ?? "📣" });
      stop();
      timer = setTimeout(() => { timer = null; show(null); }, ms ? 6500 : 5500);
    },
    stop,
  };
}
