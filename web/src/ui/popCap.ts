// "Chits per world" in the Brains dialog: hold every world of this game at so many chits.
//
// A model that keeps up with about 20 chits drove 2% of a world of 90. The limit pauses births while a world is at or
// over it; nobody is removed, so a bigger world shrinks as its old die.

export type PopCap = { cap: number | null; min: number; island: number | null };

export function validCap(n: number, pc: PopCap): boolean {
  return Number.isInteger(n) && n >= pc.min && n <= (pc.island ?? n);
}

export function popCapText(pc: PopCap): string {
  if (pc.cap != null) {
    return `Each world is held at ${pc.cap} chits. Nobody is removed: births pause until a world is below ${pc.cap}.`;
  }
  return `No limit beyond the island's own (${pc.island ?? "?"}). A world with more chits than its model keeps up with leaves most decisions to instinct.`;
}
