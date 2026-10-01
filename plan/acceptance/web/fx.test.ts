import { signGlyph, villageLabelVisible, weatherProfile } from "../../../web/src/render/fx";

test("weather profiles", () => {
  expect(weatherProfile("storm", "autumn")).toEqual({ particles: "rain", count: 420, tint: 0x1a2238, tintAlpha: 0.38, lightning: true, wind: 2.2 });
  expect(weatherProfile("rain", "winter").particles).toBe("rain");
  expect(weatherProfile("drought", "summer")).toMatchObject({ particles: "none", tint: 0xd9a441, lightning: false });
  expect(weatherProfile("snow", "winter")).toMatchObject({ particles: "snow", count: 260 });
  expect(weatherProfile("clear", "winter")).toMatchObject({ particles: "snow", count: 120, tintAlpha: 0 });
  expect(weatherProfile("clear", "autumn").particles).toBe("leaves");
  expect(weatherProfile("clear", "spring").particles).toBe("petals");
  expect(weatherProfile("clear", "summer").particles).toBe("fireflies");
  expect(weatherProfile("volcano", "spring")).toEqual({ particles: "none", count: 0, tint: 0, tintAlpha: 0, lightning: false, wind: 0 });
});

test("glyphs and labels", () => {
  expect(signGlyph("clay")).toBe("🟫");
  expect(signGlyph("danger")).toBe("⚠️");
  expect(signGlyph("nope")).toBe("❔");
  expect(villageLabelVisible(2)).toBe(true);
  expect(villageLabelVisible(3)).toBe(false);
});
