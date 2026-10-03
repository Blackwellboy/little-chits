import { describe, expect, it } from "vitest";
import { entryLines, type Entry } from "../../web/src/ui/encyclopedia";

// 📖 the Knowledge tab's encyclopedia: an entry from the server, as labelled lines
describe("entryLines", () => {
  const base = { world: "A", first_by: "Wura", first_day: 2, undiscovered_uses: 0 };

  it("says what an item is made from, what it does and what it goes into", () => {
    const axe: Entry = {
      ...base, key: "recipe:stone_axe", kind: "recipe", name: "stone axe", icon: "🪓", props: ["tool", "cuts wood"],
      made_from: { inputs: [{ key: "cord", name: "cord", n: 1 }, { key: "wood", name: "wood", n: 2 }], station: "workshop", makes: 2 },
      effects: ["Tool: works as an axe with power 2.", "Helps to gather wood."],
      used_in_recipes: [{ key: "x", name: "copper axe" }], used_in_buildings: [{ key: "hut", name: "hut", n: 8 }, { key: "pen", name: "pen", n: 1 }],
      undiscovered_uses: 3,
    };
    expect(entryLines(axe)).toEqual([
      { label: "Properties", text: "tool, cuts wood" },
      { label: "Made from", text: "cord + 2 wood, at a workshop (makes 2)" },
      { label: "Effect", text: "Tool: works as an axe with power 2." },
      { label: "Effect", text: "Helps to gather wood." },
      { label: "Used to make", text: "copper axe" },
      { label: "Used to build", text: "hut (takes 8), pen (takes 1)" },
      { label: "Still unknown", text: "3 more uses this world has not found yet." },
    ]);
  });

  it("leaves out what the server did not send", () => {
    const cord: Entry = { ...base, key: "recipe:cord", kind: "recipe", name: "cord", icon: "🧵", props: ["strong"],
      made_from: { inputs: [{ key: "fiber", name: "plant fiber", n: 2 }], station: null, makes: 1 }, effects: [],
      used_in_recipes: [], used_in_buildings: [], undiscovered_uses: 1 };
    expect(entryLines(cord).map((l) => l.label)).toEqual(["Properties", "Made from", "Still unknown"]);
    expect(entryLines(cord)[1].text).toBe("2 plant fiber");
    expect(entryLines(cord)[2].text).toBe("1 more use this world has not found yet.");
  });

  it("says who invented a world's own invention", () => {
    const inv: Entry = { ...base, key: "recipe:inv_a_1", kind: "recipe", name: "wolf stick", icon: "💡", props: [],
      invention: { purpose: "defence", purpose_text: "", by: "Wura", day: 3 } };
    expect(entryLines(inv)[0]).toEqual({ label: "Invention", text: "Wura invented it on day 3, for defence." });
  });

  it("says what a building does, what it takes and how big it is", () => {
    const hall: Entry = { ...base, key: "design:town_hall", kind: "design", name: "town hall", icon: "",
      blurb: "the heart of a town", materials: [{ key: "brick", name: "brick", n: 16 }, { key: "glass", name: "glass", n: 2 }],
      size: [3, 2], min_pop: 20, made_here: [] };
    expect(entryLines(hall)).toEqual([
      { label: "What it does", text: "The heart of a town." },
      { label: "Materials", text: "16 brick, 2 glass" },
      { label: "Size", text: "3 by 2 tiles" },
      { label: "Needs", text: "a village of 20 or more" },
    ]);
  });
});
