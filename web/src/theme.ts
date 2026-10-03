/**
 * Themes: the one place the observer's look and branding are chosen. The server says which theme it runs
 * (`theme` in the hello message and /api/health; CHITS_THEME=norse); `?theme=norse|default` in the URL overrides it.
 * Renderers and panels ask `theme()` (or `themeFor(id)`) instead of testing for a theme themselves.
 */
import * as A from "./render/art";
import { PAINTERS, type Painter } from "./render/buildings";
import * as N from "./render/norse";

export type ThemeId = "default" | "norse";
export const THEME_IDS: ThemeId[] = ["default", "norse"];
type EyeKind = "open" | "blink" | "sleep" | "happy";
type Placeable = { x: number; y: number; scale: { y: number; copyFrom(p: any): unknown } };

export type Theme = {
  id: ThemeId;
  title: string; // the tab's title
  brand: string; // top bar, boot card, recording watermark
  subtitle?: string; // under the brand on the boot card
  welcome: { eyebrow?: string; heading: string; body: string[]; watch: string };
  terrain: A.TerrainPalette;
  painters: Record<string, Painter>;
  tree: (variant: number, size: number) => HTMLCanvasElement;
  bush: (berries: number, variant: number, winter?: boolean) => HTMLCanvasElement;
  chit: {
    /** A body sprite: its texture cache key, how to paint it, and the tint applied on top. */
    body: (hue: number) => { key: string; paint: () => HTMLCanvasElement; tint: number };
    outline: () => HTMLCanvasElement;
    eyes: (kind: EyeKind) => HTMLCanvasElement;
    placeEyes: (eyes: Placeable, body: Placeable, bob: number, sleeping: boolean, moving: boolean) => void;
    portrait: (hue: number) => HTMLCanvasElement; // the coloured 14×14 body
    portraitEyesY: number;
    dot: (hue: number) => string; // on the minimap
  };
};

const DEFAULT: Theme = {
  id: "default",
  title: "Little Chits",
  brand: "LITTLE CHITS",
  welcome: {
    heading: "Welcome to Little Chits",
    body: ["Tiny creatures wake up on an island knowing almost nothing. They get hungry and cold, experiment with what "
      + "they find, build, teach each other and grow old. An AI model is the mind inside each chit: put different "
      + "models in two identical worlds and watch how differently their civilisations grow."],
    watch: "Watch",
  },
  terrain: A.DEFAULT_TERRAIN,
  painters: PAINTERS,
  tree: A.treeCanvas,
  bush: A.bushCanvas,
  chit: {
    body: (hue) => ({ key: "body", paint: A.chitBody, tint: A.hsl(hue, 58, 64) }),
    outline: A.chitOutline,
    eyes: A.chitEyes,
    placeEyes: (eyes, _body, bob, sleeping, moving) => {
      eyes.y = -bob - (sleeping ? 5 : 8.5);
      eyes.x = moving ? 1 : 0;
    },
    portrait: A.tintedChitBody,
    portraitEyesY: 10,
    dot: (hue) => `hsl(${hue} 70% 65%)`,
  },
};

const NORSE: Theme = {
  id: "norse",
  title: "Fjordfolk — small lives, long sagas",
  brand: "FJORDFOLK",
  subtitle: "Small lives. Long sagas.",
  welcome: {
    eyebrow: "A Nordic-inspired world",
    heading: "Welcome to Fjordfolk",
    body: [
      "Build a settlement beside pine woods and cold fjord water. Your villagers gather resources, build timber "
      + "halls and pass discoveries to the next generation.",
      "An AI model is the mind inside each villager: put different models in two identical worlds and watch how "
      + "differently their sagas unfold.",
    ],
    watch: "Watch the settlement",
  },
  terrain: N.NORSE_TERRAIN,
  painters: N.NORSE_PAINTERS,
  tree: N.treeCanvas,
  bush: N.bushCanvas,
  chit: {
    // painted in its wool colour, not tinted
    body: (hue) => ({ key: `folk:${N.folkVariant(hue)}`, paint: () => N.chitBody(hue), tint: 0xffffff }),
    outline: N.chitOutline,
    eyes: N.chitEyes,
    placeEyes: (eyes, body, bob) => {
      eyes.y = -bob - 10.5 * body.scale.y;
      eyes.scale.copyFrom(body.scale);
      eyes.x = 0; // on the face, not on the cloak
    },
    portrait: N.chitBody,
    portraitEyesY: 9,
    dot: N.folkCloth,
  },
};

const THEMES: Record<ThemeId, Theme> = { default: DEFAULT, norse: NORSE };

export function themeFor(id: string | null | undefined): Theme {
  return THEMES[id as ThemeId] ?? DEFAULT;
}

/** The theme to show: a valid `?theme=` in the URL, else the server's, else the default. */
export function pickTheme(server: string | null | undefined, search = ""): ThemeId {
  const asked = new URLSearchParams(search).get("theme");
  if (asked && asked in THEMES) return asked as ThemeId;
  return server && server in THEMES ? (server as ThemeId) : "default";
}

let current: Theme = DEFAULT;

export function theme(): Theme {
  return current;
}

/** Switch theme; true if it changed. Under the default theme the page is left exactly as it is. */
export function setTheme(id: ThemeId): boolean {
  const next = themeFor(id);
  if (next === current) return false;
  current = next;
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = next.id;
    document.title = next.title;
  }
  return true;
}
