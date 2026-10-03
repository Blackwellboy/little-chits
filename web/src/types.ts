export type Clock = {
  tick: number; day: number; year: number; season: "spring" | "summer" | "autumn" | "winter";
  hour: number; daylight: number; night: boolean; day_of_season: number;
  weather?: string; era?: string;
};

export type AgentBrief = {
  id: string; name: string; x: number; y: number; hue: number; act: string; emote: string; say: string;
  think: boolean; carry: string | null; tool: string | null; child: boolean; basket: boolean; hp: number;
  hunger: number; brain: string; src: "model" | "instinct";
};

export type StructureView = {
  id: string; design: string; name: string; x: number; y: number; w: number; h: number; complete: boolean;
  progress: number; needs: Record<string, number>; durability: number; lit: boolean; fuel: number;
  planted: boolean; growth: number; stored: number; storage: Record<string, number> | null; tablets: number;
  founder: string | null; builders: number; ruined: boolean;
  // a station someone is working a shift at until this tick (compare with the clock), and its output so far
  worked_until?: number; produced?: Record<string, number> | null;
  // a home being rebuilt bigger where it stands: into what, what it still needs, how far the work is
  upgrade?: { to: string; name: string; needs: Record<string, number>; progress: number } | null;
};

export type WorldEvent = {
  seq: number; tick: number; kind: string; text: string; importance: number; actor: string | null;
  x: number | null; y: number | null; data: Record<string, any>;
};

export type Stats = {
  tick: number; day: number; population: number; deaths: number; structures: number; sites: number;
  by_design: Record<string, number>; knowledge: number; discoveries: number; roads: number; tablets: number;
  stored: number; avg_hunger: number; generations: number; era?: string;
};

export type WorldMeta = {
  id: string; name: string; label: string; culture: "direct" | "stigmergy"; flags: Record<string, boolean>;
  size: number; seed: number;
};

export type BrainSummary = {
  id: string; label: string; thinking: number; healthy: boolean; tok_s: number; latency_ms: number;
};

export type Control = {
  contract?: "play" | "experiment"; mode?: string; contact?: boolean; sandbox_modified?: boolean;
  skip?: import("./ui/skip").SkipState | null; last_skip?: import("./ui/skip").SkipResult | null;
  speed: number; paused: boolean; tps: number; pace_to_brain: boolean; waiting_on_brain: boolean; speeds: number[];
};

export type AgentDetail = AgentBrief & {
  alive: boolean; age: number; generation: number; parents: (string | null)[]; died: number; cause: string;
  needs: { hunger: number; energy: number; warmth: number; health: number; mood: number };
  traits: Record<string, number>; personality: string;
  inventory: { key: string; name: string; n: number; icon: string; tool: boolean }[];
  load: number; capacity: number;
  knows: { key: string; kind: string; name: string; how: string; from: string | null; day: number; detail: string; icon: string }[];
  lessons: string[]; failed: string[];
  memories: { tick: number; text: string; importance: number; kind: string }[];
  relations: { id: string; name: string; affinity: number }[];
  skills: Record<string, number>; goal: string; thought: string; plan: string[];
  plan_state: { desc: string; reflex: boolean; filler: boolean }[];
  last_choice?: { tick: number; chose: string; confidence: number | null; escalated: boolean; why?: string;
    options: { letter: string; goal: string; p: number }[] } | null;
  plan_source: string; last_result: string; brain_label: string; plan_id?: string; objective?: string; objective_since?: number;
  home: { id: string; name: string; x: number; y: number } | null;
  stats: Record<string, number>; decisions: number;
  want?: string; renown?: number; famous?: boolean;
};
