/** The Look button (classic / Fjordfolk, the Norse theme). The server refuses a switch during an experiment run (new
 *  chits' names reach the models' prompts), and the button used to swallow that refusal: it did nothing at all. It now
 *  says so before the click, and any other refusal is said out loud. */
export type LookState = { next: "default" | "norse"; disabled: boolean; title: string; label: string; glyph: string };

export function lookButton(theme: string, contract: string | undefined): LookState {
  const norse = theme === "norse";
  const next = norse ? "default" : "norse";
  if (contract === "experiment") {
    return { next, disabled: true, label: norse ? "norse" : "classic", glyph: norse ? "ᚠ" : "●",
      title: "Look: locked during an experiment run (new chits' names reach the models). End the experiment (🧪) or start a play game to switch it." };
  }
  return { next, disabled: false, label: norse ? "norse" : "classic", glyph: norse ? "ᚠ" : "●",
    title: norse ? "Look: Fjordfolk, the Norse theme (click for the classic look)"
      : "Look: classic (click for Fjordfolk, the Norse theme: Nordic art, and Norse names for chits born from now on)" };
}
