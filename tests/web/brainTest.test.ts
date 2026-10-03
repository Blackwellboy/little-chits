import { describe, expect, it } from "vitest";
import { TestResult, fixBody, saveBody, testLines, took } from "../../web/src/ui/brainTest";

// The Brains dialog's Test explains itself: the reply, whether it was a plan, the one-token choice, how long it
// took, and for each problem a plain cause with its one-click fix.
const good: TestResult = {
  ok: true, model: "qwen", reply: '{"thought": "Food first.", "goal": "eat", "plan": []}', latency_ms: 4200, parsed: true,
  plan: { goal: "eat", steps: ["gather", "eat"] }, logprobs: true, choice: "B", choice_latency_ms: 310, findings: [], error: "", detected: null,
};

describe("testLines", () => {
  it("shows the reply, the plan, the choice and the time", () => {
    const lines = testLines(good).map((l) => `${l.mark} ${l.text}`);
    expect(lines).toEqual([
      '✓ qwen replied in 4.2 s: “{"thought": "Food first.", "goal": "eat", "plan": []}”',
      "✓ The reply is a plan: eat (gather → eat).",
      "✓ One-token choice with logprobs: B, in 310 ms.",
      "✓ This brain can decide for chits.",
    ]);
  });
  it("gives each problem its cause and its fix", () => {
    const r: TestResult = {
      ...good, ok: false, reply: "", parsed: false, plan: null, logprobs: false, choice: "",
      findings: [
        { code: "thinking", level: "fail", text: "The model spent its reply thinking and never gave an answer.", fix: { label: "Disable thinking", patch: { disable_thinking: true } } },
        { code: "no_logprobs", level: "note", text: "The server sent no logprobs with the one-token choice.", fix: null },
      ],
    };
    const lines = testLines(r);
    expect(lines[0]).toEqual({ mark: "✗", text: "qwen replied in 4.2 s with nothing." });
    expect(lines[1]).toEqual({ mark: "✗", text: "The model spent its reply thinking and never gave an answer.", fix: { label: "Disable thinking", patch: { disable_thinking: true } } });
    expect(lines[2]).toEqual({ mark: "·", text: "The server sent no logprobs with the one-token choice." });
    expect(lines.some((l) => l.text === "This brain can decide for chits.")).toBe(false);
  });
  it("marks a problem that only slows the brain differently from one that stops it", () => {
    const r: TestResult = { ...good, findings: [{ code: "json_refused", level: "warn", text: "The server refused JSON mode. The request worked without it.", fix: { label: "Turn JSON mode off", patch: { json_mode: false } } }] };
    const warn = testLines(r).find((l) => l.fix);
    expect(warn?.mark).toBe("!");
    expect(testLines(r).some((l) => l.text === "This brain can decide for chits.")).toBe(false);
  });
  it("says which settings a first test found", () => {
    const lines = testLines({ ...good, detected: { json_mode: false, disable_thinking: true } });
    expect(lines.map((l) => l.text)).toContain("Settings found for this server: JSON mode off, skip-thinking switch on.");
  });
  it("still shows a bare error (a request the game server refused)", () => {
    expect(testLines({ ok: false, error: "no such brain" })).toEqual([{ mark: "✗", text: "no such brain" }]);
  });
  it("writes times the short way", () => {
    expect(took(850)).toBe("850 ms");
    expect(took(12345)).toBe("12.3 s");
  });
});

describe("fixBody", () => {
  it("changes only what the fix names", () => {
    expect(fixBody({ id: "m1", base_url: "http://127.0.0.1:1/v1", label: "M", max_tokens: 600 } as any, { label: "Turn JSON mode off", patch: { json_mode: false } }))
      .toEqual({ id: "m1", base_url: "http://127.0.0.1:1/v1", json_mode: false });
  });
});

describe("saveBody", () => {
  const form = { id: "", label: "M", base_url: "http://127.0.0.1:1/v1", model: "", api_key: "", max_concurrency: "4", temperature: "0.7", max_tokens: "600" };
  it("leaves JSON mode and the thinking switch to the first test for a new brain", () => {
    const body = saveBody(form);
    expect("json_mode" in body || "disable_thinking" in body).toBe(false);
    expect(body.max_concurrency).toBe(4);
  });
  it("sends them once the user has set them", () => {
    expect(saveBody({ ...form, json_mode: true, disable_thinking: false, touched: true })).toMatchObject({ json_mode: true, disable_thinking: false });
    expect("touched" in saveBody({ ...form, touched: true })).toBe(false);
  });
  it("keeps a tested brain's settings when it is edited, and an untested one's to be found", () => {
    expect(saveBody({ ...form, id: "m1", json_mode: true, disable_thinking: true, detect: false })).toMatchObject({ json_mode: true, disable_thinking: true });
    const pending = saveBody({ ...form, id: "m1", json_mode: false, disable_thinking: false, detect: true });
    expect("json_mode" in pending || "detect" in pending).toBe(false);
  });
});
