/** "Why is nothing happening?": the server's diagnostics as plain sentences (GET /api/why). Pure, for testing. */
export type WhyReason = { kind: string; text: string };
export type WhyData = {
  game: WhyReason[];
  worlds: Record<string, { name: string; day: number | null; brain: string; reasons: WhyReason[] }>;
};

export const WHY_NOTHING = "Nothing is holding this world back right now.";

/** The lines for one world: what stops the whole game first, then that world's own reasons. */
export function whyLines(d: WhyData, world: string): WhyReason[] {
  return [...(d.game ?? []), ...(d.worlds?.[world]?.reasons ?? [])];
}
