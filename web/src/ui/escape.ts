/** Escape, one layer at a time: whatever is on top (an open menu, then an armed god-mode tool, then the Inspector)
 *  takes it, and nothing under it sees the same key press. Every listener used to act on its own, so one Escape
 *  closed the ⋯ menu and the Inspector together, and which went first hung on which component mounted first. */

export type EscapeLayer = { rank: number; handle: () => boolean };  // handle: true when it took the key press

/** The ranks: higher goes first. */
export const ESC_MENU = 30, ESC_GOD_TOOL = 20, ESC_INSPECTOR = 10;

const layers: EscapeLayer[] = [];

/** A key press in a form control is the control's: Escape in a <select> or a text box closes nothing else. */
export function isFormControl(el: { tagName?: string; isContentEditable?: boolean } | null | undefined): boolean {
  return !!el && (["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName ?? "") || !!el.isContentEditable);
}

/** Offer an Escape to the layers, highest rank first (the latest added first among equals); true once one took it. */
export function dispatchEscape(ls: EscapeLayer[], target: { tagName?: string; isContentEditable?: boolean } | null): boolean {
  if (isFormControl(target)) return false;
  const order = ls.map((l, i) => [l, i] as const).sort((a, b) => b[0].rank - a[0].rank || b[1] - a[1]);
  return order.some(([l]) => l.handle());
}

/** Add a layer; the returned function removes it (an effect's cleanup). */
export function onEscape(rank: number, handle: () => boolean): () => void {
  const l = { rank, handle };
  layers.push(l);
  return () => { const i = layers.indexOf(l); if (i >= 0) layers.splice(i, 1); };
}

if (typeof window !== "undefined") {
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (dispatchEscape(layers, e.target as HTMLElement | null)) { e.preventDefault(); e.stopPropagation(); }
  }, true);
}
