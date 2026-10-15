// 🚀 The space programme (server sim/space.py) as the Progress panel says it. Pure: no React.

export type SpaceProgramme = {
  launches: number; satellites: number; moon_day: number | null; station_day: number | null; expeditions: number;
  next: string; rockets: number;
};

const NEXT: Record<string, string> = {
  satellite: "a satellite circling the island",
  moon: "a landing on the Moon",
  station: "a station in orbit",
  expedition: "an expedition beyond the Moon",
};

/** The headline ("3 launches") and what is up there, in order. */
export function spaceLines(sp: SpaceProgramme | null | undefined): { head: string; done: string[]; next: string } | null {
  if (!sp || !sp.launches) return null;
  const done: string[] = [];
  if (sp.satellites) done.push(sp.satellites === 1 ? "a satellite" : `${sp.satellites} satellites`);
  if (sp.moon_day != null) done.push(`the Moon (day ${sp.moon_day})`);
  if (sp.station_day != null) done.push(`a station in orbit (day ${sp.station_day})`);
  if (sp.expeditions) done.push(sp.expeditions === 1 ? "1 expedition" : `${sp.expeditions} expeditions`);
  const head = `${sp.launches} launch${sp.launches === 1 ? "" : "es"}`;
  const what = NEXT[sp.next] ?? "";
  const next = what ? `Next launch: ${what}${sp.rockets ? " (a rocket is ready)" : ""}.` : "";
  return { head, done, next };
}

/** Events that send a rocket up over the pad in the world view: the first launch and every mission after it. */
export function launchEvent(kind: string): boolean {
  return kind === "launch" || kind === "space";
}
