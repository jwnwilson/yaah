import type { AuditEvent, RunEvent, RunUsage, UsageRecord } from "@/lib/api/types";
import { costByStage, isNarration, segmentRounds } from "./runTimeline";

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

let seq = 0;
function at(n: number): string {
  // monotonic ISO timestamps; n orders the merged stream
  return new Date(Date.UTC(2026, 5, 17, 0, 0, n)).toISOString();
}

function ev(over: Partial<RunEvent> & Pick<RunEvent, "type">): RunEvent {
  return {
    id: `e${seq++}`,
    run_id: "r1",
    stage: null,
    message: "",
    created_at: at(seq),
    ...over,
  };
}

function aud(over: Partial<AuditEvent> & Pick<AuditEvent, "action">): AuditEvent {
  return {
    id: `a${seq++}`,
    run_id: "r1",
    stage: null,
    actor: "lead",
    detail: {},
    created_at: at(seq),
    ...over,
  };
}

// ---------------------------------------------------------------------------
// isNarration
// ---------------------------------------------------------------------------

describe("isNarration", () => {
  test("treats agent_event as narration", () => {
    expect(isNarration("agent_event")).toBe(true);
  });

  test("treats every other type as a milestone", () => {
    for (const t of [
      "stage_started",
      "stage_completed",
      "agent_dispatched",
      "agent_reported",
      "monitor_started",
      "monitor_verdict",
      "gate_opened",
      "gate_resolved",
      "blocked",
      "quiescence_reached",
      "error",
    ] as const) {
      expect(isNarration(t)).toBe(false);
    }
  });
});

// ---------------------------------------------------------------------------
// costByStage
// ---------------------------------------------------------------------------

describe("costByStage", () => {
  function rec(over: Partial<UsageRecord>): UsageRecord {
    return {
      stage: "implement",
      model_id: "m",
      agent_role: "backend",
      input_tokens: 0,
      output_tokens: 0,
      cost_usd: 0,
      ...over,
    };
  }

  test("sums tokens and cost per stage and a grand total", () => {
    // Arrange
    const usage: RunUsage = {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_creation_tokens: 0,
      cost_usd: 0,
      total_tokens: 0,
      breakdown: [
        rec({ stage: "plan", input_tokens: 10, output_tokens: 1, cost_usd: 0.1 }),
        rec({ stage: "implement", input_tokens: 20, output_tokens: 2, cost_usd: 0.2 }),
        rec({ stage: "implement", input_tokens: 5, output_tokens: 3, cost_usd: 0.05 }),
      ],
    };

    // Act
    const result = costByStage(usage);

    // Assert
    const plan = result.perStage.find((s) => s.stage === "plan");
    const implement = result.perStage.find((s) => s.stage === "implement");
    expect(plan).toMatchObject({ cost_usd: 0.1, input_tokens: 10, output_tokens: 1 });
    expect(implement).toMatchObject({ input_tokens: 25, output_tokens: 5 });
    expect(implement?.cost_usd).toBeCloseTo(0.25);
    expect(result.total).toMatchObject({ input_tokens: 35, output_tokens: 6 });
    expect(result.total.cost_usd).toBeCloseTo(0.35);
  });

  test("returns an empty breakdown and zero total when there are no records", () => {
    const usage: RunUsage = {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_creation_tokens: 0,
      cost_usd: 0,
      total_tokens: 0,
      breakdown: [],
    };
    const result = costByStage(usage);
    expect(result.perStage).toEqual([]);
    expect(result.total).toEqual({ cost_usd: 0, input_tokens: 0, output_tokens: 0 });
  });
});

// ---------------------------------------------------------------------------
// segmentRounds
// ---------------------------------------------------------------------------

describe("segmentRounds", () => {
  test("splits a scripted stream into setup, rounds and wrap-up", () => {
    seq = 0;
    // Arrange: provision setup -> round 1 (plan/implement/verify+verdict)
    //          -> round 2 (plan/implement/verify+verdict) -> wrapup (pr/learn)
    const events: RunEvent[] = [
      ev({ type: "stage_started", stage: "provision", message: "provisioning" }),
      // round 1
      ev({ type: "stage_started", stage: "plan", message: "lead plans" }),
      ev({ type: "agent_event", stage: "plan", message: "thinking about plan" }),
      ev({ type: "agent_dispatched", stage: "implement", message: "dispatch backend", agent_id: "ag1" }),
      ev({ type: "agent_event", stage: "implement", message: "writing code" }),
      ev({ type: "quiescence_reached", stage: "implement", message: "all idle" }),
      ev({ type: "monitor_started", stage: "verify", message: "monitor checks" }),
      ev({ type: "monitor_verdict", stage: "verify", message: "rejected: needs work" }),
      // round 2
      ev({ type: "stage_started", stage: "plan", message: "lead replans" }),
      ev({ type: "agent_event", stage: "implement", message: "fixing" }),
      ev({ type: "monitor_verdict", stage: "verify", message: "accepted" }),
      // wrapup
      ev({ type: "stage_started", stage: "pr", message: "opening PR" }),
      ev({ type: "stage_completed", stage: "learn", message: "memory updated" }),
    ];
    const audit: AuditEvent[] = [
      aud({ action: "capability_granted", stage: "implement", detail: { tools: ["edit"] } }),
      aud({ action: "tool_allowed", stage: "implement", detail: { tool: "edit" } }),
      aud({ action: "tool_denied", stage: "implement", detail: { tool: "bash", reason: "blocked" } }),
    ];
    // interleave audit timestamps within round 1 implement: place them after the
    // dispatch event by adjusting created_at to fall between events.
    audit[0].created_at = events[3].created_at; // grant ~ dispatch time
    audit[1].created_at = events[4].created_at;
    audit[2].created_at = events[4].created_at;

    // Act
    const rounds = segmentRounds(events, audit);

    // Assert: keys/order
    expect(rounds.map((r) => r.key)).toEqual(["setup", "round-1", "round-2", "wrapup"]);

    const setup = rounds[0];
    expect(setup.stages.map((s) => s.stage)).toEqual(["provision"]);

    const round1 = rounds[1];
    // stages appear in first-seen order
    expect(round1.stages.map((s) => s.stage)).toEqual(["plan", "implement", "verify"]);
    const r1implement = round1.stages.find((s) => s.stage === "implement")!;
    expect(r1implement.grant?.action).toBe("capability_granted");
    expect(r1implement.narration.map((n) => n.message)).toEqual(["writing code"]);
    expect(r1implement.decisions.map((d) => d.action)).toEqual(["tool_allowed", "tool_denied"]);
    // the verdict closes round 1 and belongs to it
    const r1verify = round1.stages.find((s) => s.stage === "verify")!;
    expect(r1verify.milestones.some((m) => m.type === "monitor_verdict")).toBe(true);

    const round2 = rounds[2];
    expect(round2.stages.map((s) => s.stage)).toEqual(["plan", "implement", "verify"]);
    const r2implement = round2.stages.find((s) => s.stage === "implement")!;
    expect(r2implement.narration.map((n) => n.message)).toEqual(["fixing"]);

    const wrapup = rounds[3];
    expect(wrapup.key).toBe("wrapup");
    expect(wrapup.stages.map((s) => s.stage)).toEqual(["pr", "learn"]);
  });

  test("a monitor_verdict closes the current round so later items open a new one", () => {
    seq = 0;
    const events: RunEvent[] = [
      ev({ type: "stage_started", stage: "plan", message: "plan A" }),
      ev({ type: "monitor_verdict", stage: "verify", message: "rejected" }),
      ev({ type: "stage_started", stage: "plan", message: "plan B" }),
    ];
    const rounds = segmentRounds(events, []);
    expect(rounds.map((r) => r.key)).toEqual(["round-1", "round-2"]);
  });

  test("collects an unsegmentable tail after wrap-up under an 'other' group", () => {
    seq = 0;
    const events: RunEvent[] = [
      ev({ type: "stage_started", stage: "plan", message: "plan" }),
      ev({ type: "monitor_verdict", stage: "verify", message: "accepted" }),
      ev({ type: "stage_started", stage: "pr", message: "pr" }),
      // an unexpected non-pr/learn event after wrap-up
      ev({ type: "error", stage: null, message: "post-wrapup failure" }),
    ];
    const rounds = segmentRounds(events, []);
    const keys = rounds.map((r) => r.key);
    expect(keys).toContain("other");
    const other = rounds.find((r) => r.key === "other")!;
    const flat = other.stages.flatMap((s) => s.milestones.map((m) => m.message));
    expect(flat).toContain("post-wrapup failure");
  });

  test("returns no rounds for an empty stream", () => {
    expect(segmentRounds([], [])).toEqual([]);
  });
});
