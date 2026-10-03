import { describe, expect, it } from "vitest";
import * as A from "../../web/src/render/art";
import { PAINTERS } from "../../web/src/render/buildings";
import * as N from "../../web/src/render/norse";
import { pickTheme, setTheme, theme, themeFor, THEME_IDS } from "../../web/src/theme";

// The default look as it was before themes: the default theme must keep exactly these colours.
const ORIGINAL_TILES = {
  0: ["#1c4a82", "#173f72"], 1: ["#2f86bd", "#2a78ab"], 2: ["#e8d49a", "#dcc486"], 3: ["#6fae4f", "#63a046"],
  4: ["#8cc053", "#7fb34a"], 5: ["#4a8a3a", "#3f7a31"], 6: ["#98a95f", "#8a9b54"], 7: ["#7f8189", "#6f7179"],
  8: ["#b8704e", "#a86244"],
};
const ORIGINAL_PREVIEW = {
  0: "#1b4880", 1: "#2e82b8", 2: "#e2cc92", 3: "#6aa84c", 4: "#86ba50", 5: "#467f37", 6: "#93a45c", 7: "#7b7d85", 8: "#b06a4a",
};
const ORIGINAL_MINIMAP = {
  0: "#1c4a82", 1: "#2f86bd", 2: "#e0cc92", 3: "#6fae4f", 4: "#8cc053", 5: "#3f7a31", 6: "#98a95f", 7: "#7f8189", 8: "#b8704e",
};
const RESTYLED = ["hut", "brick_house", "longhouse", "two_storey_house", "library", "great_library", "school",
  "lighthouse", "workshop", "well", "granary", "warehouse", "smithy", "watchtower"];

const sprite = () => ({ x: 0, y: 0, scale: { y: 0.8, copyFrom(p: { y: number }) { this.y = p.y; } } });

describe("themes", () => {
  it("the default theme is the original look: same palette, same art, same buildings", () => {
    const t = themeFor("default");
    expect(t.terrain.tiles).toEqual(ORIGINAL_TILES);
    expect(t.terrain.preview).toEqual(ORIGINAL_PREVIEW);
    expect(t.terrain.minimap).toEqual(ORIGINAL_MINIMAP);
    expect(t.terrain.flowers).toEqual(["#fff6c2", "#ffd3e8", "#f7e26b", "#ffffff"]);
    expect(t.terrain).toBe(A.DEFAULT_TERRAIN);
    expect(t.painters).toBe(PAINTERS);
    expect([t.tree, t.bush]).toEqual([A.treeCanvas, A.bushCanvas]);
    expect([t.chit.outline, t.chit.eyes, t.chit.portrait]).toEqual([A.chitOutline, A.chitEyes, A.tintedChitBody]);
    // one grey body for everyone, tinted by hue as before (hsl(0, 58%, 64%) is #d86e6e)
    const body = t.chit.body(0);
    expect(body).toEqual({ key: "body", paint: A.chitBody, tint: 0xd86e6e });
    expect(t.chit.body(200).key).toBe("body");
    expect(t.chit.dot(200)).toBe("hsl(200 70% 65%)");
    expect(t.chit.portraitEyesY).toBe(10);
    const eyes = sprite();
    t.chit.placeEyes(eyes, sprite(), 2, false, true);
    expect([eyes.x, eyes.y, eyes.scale.y]).toEqual([1, -10.5, 0.8]);
    t.chit.placeEyes(eyes, sprite(), 0, true, false);
    expect([eyes.x, eyes.y]).toEqual([0, -5]);
    expect([t.brand, t.title, t.subtitle, t.welcome.heading, t.welcome.eyebrow, t.welcome.watch])
      .toEqual(["LITTLE CHITS", "Little Chits", undefined, "Welcome to Little Chits", undefined, "Watch"]);
  });

  it("the Norse theme brings the Nordic palette, villagers and halls", () => {
    const t = themeFor("norse");
    expect(t.terrain).toBe(N.NORSE_TERRAIN);
    expect(t.terrain.tiles[A.DEEP]).toEqual(["#254b64", "#203f58"]);
    expect(t.terrain.preview).toBe(N.TERRAIN_COLORS);
    expect(t.terrain.minimap).toBe(N.TERRAIN_COLORS);
    expect(t.terrain.tiles).not.toEqual(ORIGINAL_TILES);
    // every building still has a painter; the halls are restyled, the rest are the default ones
    expect(Object.keys(t.painters).sort()).toEqual(Object.keys(PAINTERS).sort());
    for (const k of Object.keys(PAINTERS)) {
      if (RESTYLED.includes(k)) expect(t.painters[k], k).not.toBe(PAINTERS[k]);
      else expect(t.painters[k], k).toBe(PAINTERS[k]);
    }
    expect([t.tree, t.bush]).toEqual([N.treeCanvas, N.bushCanvas]);
    expect([t.chit.outline, t.chit.eyes, t.chit.portrait]).toEqual([N.chitOutline, N.chitEyes, N.chitBody]);
    // painted in wool colours, so no tint; one texture per colour
    expect(t.chit.body(0)).toMatchObject({ key: "folk:0", tint: 0xffffff });
    expect(t.chit.body(200).key).toBe("folk:4");
    expect(t.chit.dot(0)).toBe(N.FOLK_CLOTH[0]);
    expect([N.folkVariant(-1), N.folkVariant(360), N.folkVariant(359)]).toEqual([7, 0, 7]);
    // eyes sit on the face and squash with the body
    const eyes = sprite(), body = sprite();
    t.chit.placeEyes(eyes, body, 2, false, true);
    expect([eyes.x, eyes.y, eyes.scale.y]).toEqual([0, -2 - 10.5 * 0.8, 0.8]);
    expect([t.brand, t.subtitle, t.welcome.heading]).toEqual(["FJORDFOLK", "Small lives. Long sagas.", "Welcome to Fjordfolk"]);
  });

  it("follows the server, lets ?theme= override it, and falls back to the default", () => {
    expect(THEME_IDS).toEqual(["default", "norse"]);
    expect(pickTheme("norse")).toBe("norse");
    expect(pickTheme("default")).toBe("default");
    expect(pickTheme(undefined)).toBe("default");
    expect(pickTheme("viking")).toBe("default");
    expect(pickTheme("norse", "?theme=default")).toBe("default");
    expect(pickTheme("default", "?record=1&theme=norse")).toBe("norse");
    expect(pickTheme("norse", "?theme=klingon")).toBe("norse");
    expect(themeFor("klingon").id).toBe("default");
  });

  it("setTheme switches what the renderer draws with", () => {
    expect(theme().id).toBe("default");
    expect(setTheme("default")).toBe(false);
    expect(setTheme("norse")).toBe(true);
    expect(theme().painters).toBe(N.NORSE_PAINTERS);
    expect(setTheme("norse")).toBe(false);
    expect(setTheme("default")).toBe(true);
    expect(theme().painters).toBe(PAINTERS);
  });
});
