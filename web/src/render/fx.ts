// Weather, sign and village-label rules for the renderer. Pure data, no pixi.

export type WeatherProfile = {
  particles: "rain" | "snow" | "leaves" | "petals" | "fireflies" | "none";
  count: number; tint: number; tintAlpha: number; lightning: boolean; wind: number;
};

const NONE: WeatherProfile = { particles: "none", count: 0, tint: 0, tintAlpha: 0, lightning: false, wind: 0 };
const p = (particles: WeatherProfile["particles"], count: number, tint: number, tintAlpha: number, lightning: boolean, wind: number): WeatherProfile =>
  ({ particles, count, tint, tintAlpha, lightning, wind });

const WEATHER: Record<string, WeatherProfile> = {
  rain: p("rain", 220, 0x3a4a6a, 0.18, false, 0.6),
  storm: p("rain", 420, 0x1a2238, 0.38, true, 2.2),
  drought: p("none", 0, 0xd9a441, 0.14, false, 0.2),
  snow: p("snow", 260, 0xdfe8ff, 0.1, false, 0.4),
};
const CLEAR: Record<string, WeatherProfile> = {
  winter: p("snow", 120, 0, 0, false, 0.3),
  autumn: p("leaves", 45, 0, 0, false, 0.8),
  spring: p("petals", 25, 0, 0, false, 0.5),
  summer: p("fireflies", 30, 0, 0, false, 0),
};

export function weatherProfile(weather: string, season: string): WeatherProfile {
  const w = weather === "clear" ? CLEAR[season] : WEATHER[weather];
  return { ...(w ?? NONE) };
}

const GLYPHS: Record<string, string> = {
  food: "🫐", wood: "🪵", stone: "🪨", clay: "🟫", ore: "🟠", fish: "🐟", danger: "⚠️", home: "🏠", build: "🔨", meet: "👋",
};

export function signGlyph(symbol: string): string {
  return GLYPHS[symbol] ?? "❔";
}

export function villageLabelVisible(zoom: number): boolean {
  return zoom < 2.6;
}
