/** A Brains "Test" that explains itself: the server's result (server/chits/brain/checkup.py) as lines to show. */

export type Fix = { label: string; patch: Record<string, unknown> };
export type Finding = { code: string; level: "fail" | "warn" | "note"; text: string; fix: Fix | null };
export type TestResult = {
  ok: boolean; model?: string; reply?: string | null; latency_ms?: number | null; parsed?: boolean;
  plan?: { goal: string; steps: string[] } | null; logprobs?: boolean | null; choice?: string;
  choice_latency_ms?: number | null; findings?: Finding[]; error?: string;
  detected?: { json_mode: boolean; disable_thinking: boolean } | null;
};
export type Line = { mark: "✓" | "✗" | "!" | "·"; text: string; fix?: Fix };

export function took(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

const MARK = { fail: "✗", warn: "!", note: "·" } as const;

/** What the Test found, one line each: the reply, the plan, the choice, the settings it found, then each problem
 *  with its cause (and its fix, for a button). */
export function testLines(r: TestResult): Line[] {
  const out: Line[] = [];
  const name = r.model || "The model";
  if (r.reply != null && r.latency_ms != null) {
    out.push(r.reply.trim()
      ? { mark: "✓", text: `${name} replied in ${took(r.latency_ms)}: “${r.reply.trim()}”` }
      : { mark: "✗", text: `${name} replied in ${took(r.latency_ms)} with nothing.` });
  }
  if (r.parsed && r.plan) out.push({ mark: "✓", text: `The reply is a plan: ${r.plan.goal || "no goal"} (${r.plan.steps.join(" → ")}).` });
  if (r.logprobs && r.choice) out.push({ mark: "✓", text: `One-token choice with logprobs: ${r.choice}${r.choice_latency_ms != null ? `, in ${took(r.choice_latency_ms)}` : ""}.` });
  if (r.detected) {
    out.push({ mark: "·", text: `Settings found for this server: JSON mode ${r.detected.json_mode ? "on" : "off"}, skip-thinking switch ${r.detected.disable_thinking ? "on" : "off"}.` });
  }
  for (const f of r.findings ?? []) out.push({ mark: MARK[f.level] ?? "·", text: f.text, ...(f.fix ? { fix: f.fix } : {}) });
  if (!(r.findings ?? []).length && !r.ok && r.error) out.push({ mark: "✗", text: r.error });
  if (r.ok && !(r.findings ?? []).some((f) => f.level !== "note")) out.push({ mark: "✓", text: "This brain can decide for chits." });
  return out;
}

/** The request that applies a fix: only the brain's id, its URL (the API asks for it) and the changed settings. */
export function fixBody(config: { id: string; base_url: string }, fix: Fix): Record<string, unknown> {
  return { id: config.id, base_url: config.base_url, ...fix.patch };
}

/** What a new brain's form sends: JSON mode and the thinking switch are left out until the user sets them, so the
 *  server starts the brain plain and its first Test finds what the model server takes. */
export function saveBody(form: Record<string, any>): Record<string, unknown> {
  const body: Record<string, unknown> = { ...form, max_concurrency: +form.max_concurrency, max_ai_chits: +form.max_ai_chits || 0, temperature: +form.temperature, max_tokens: +form.max_tokens };
  if (form.detect !== false && !form.touched) { delete body.json_mode; delete body.disable_thinking; }
  delete body.detect; delete body.touched;
  return body;
}
