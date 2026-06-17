import type {
  AuditEvent,
  RunEvent,
  RunEventType,
  RunStage,
  RunUsage,
} from "@/lib/api/types";

// ---------------------------------------------------------------------------
// classification
// ---------------------------------------------------------------------------

/** Only `agent_event` is streamed narration; every other type is a milestone. */
export function isNarration(type: RunEventType): boolean {
  return type === "agent_event";
}

// ---------------------------------------------------------------------------
// cost-by-stage
// ---------------------------------------------------------------------------

export interface StageCost {
  stage: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface CostByStage {
  perStage: StageCost[];
  total: { cost_usd: number; input_tokens: number; output_tokens: number };
}

const UNKNOWN_STAGE = "unknown";

/** Sum the usage breakdown rows per stage, preserving first-seen stage order. */
export function costByStage(usage: RunUsage): CostByStage {
  const order: string[] = [];
  const byStage = new Map<string, StageCost>();
  const total = { cost_usd: 0, input_tokens: 0, output_tokens: 0 };

  for (const row of usage.breakdown) {
    const stage = row.stage ?? UNKNOWN_STAGE;
    let bucket = byStage.get(stage);
    if (!bucket) {
      bucket = { stage, cost_usd: 0, input_tokens: 0, output_tokens: 0 };
      byStage.set(stage, bucket);
      order.push(stage);
    }
    bucket.cost_usd += row.cost_usd;
    bucket.input_tokens += row.input_tokens;
    bucket.output_tokens += row.output_tokens;
    total.cost_usd += row.cost_usd;
    total.input_tokens += row.input_tokens;
    total.output_tokens += row.output_tokens;
  }

  return { perStage: order.map((s) => byStage.get(s)!), total };
}

// ---------------------------------------------------------------------------
// round segmentation
// ---------------------------------------------------------------------------

export type RoundKey = "setup" | `round-${number}` | "wrapup" | "other";

export interface StageBucket {
  stage: RunStage | string | null;
  grant: AuditEvent | null;
  narration: RunEvent[];
  decisions: AuditEvent[];
  milestones: RunEvent[];
}

export interface Round {
  key: RoundKey;
  label: string;
  stages: StageBucket[];
}

/** A merged, chronologically-ordered item: either a RunEvent or an AuditEvent. */
type TimelineItem =
  | { kind: "event"; at: string; event: RunEvent }
  | { kind: "audit"; at: string; audit: AuditEvent };

const WRAPUP_STAGES: ReadonlySet<string> = new Set(["pr", "learn"]);

function mergeStreams(events: RunEvent[], audit: AuditEvent[]): TimelineItem[] {
  const items: TimelineItem[] = [
    ...events.map((event) => ({ kind: "event" as const, at: event.created_at, event })),
    ...audit.map((a) => ({ kind: "audit" as const, at: a.created_at, audit: a })),
  ];
  // Stable sort by timestamp; ties keep insertion order (events before audit at
  // the same instant only matters for bucketing, which is stage-keyed anyway).
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => (a.item.at < b.item.at ? -1 : a.item.at > b.item.at ? 1 : a.index - b.index))
    .map(({ item }) => item);
}

function itemStage(item: TimelineItem): RunStage | string | null {
  return item.kind === "event" ? item.event.stage : item.audit.stage;
}

function isProvision(item: TimelineItem): boolean {
  return itemStage(item) === "provision";
}

function isWrapup(item: TimelineItem): boolean {
  const stage = itemStage(item);
  return stage != null && WRAPUP_STAGES.has(stage);
}

function isVerdict(item: TimelineItem): boolean {
  return item.kind === "event" && item.event.type === "monitor_verdict";
}

class RoundBuilder {
  private order: string[] = [];
  private buckets = new Map<string, StageBucket>();

  add(item: TimelineItem): void {
    const stage = itemStage(item);
    const bucket = this.bucketFor(stage);
    if (item.kind === "audit") {
      if (item.audit.action === "capability_granted") bucket.grant = item.audit;
      else bucket.decisions.push(item.audit);
      return;
    }
    if (isNarration(item.event.type)) bucket.narration.push(item.event);
    else bucket.milestones.push(item.event);
  }

  build(key: RoundKey, label: string): Round {
    return { key, label, stages: this.order.map((s) => this.buckets.get(s)!) };
  }

  isEmpty(): boolean {
    return this.order.length === 0;
  }

  private bucketFor(stage: RunStage | string | null): StageBucket {
    const stageKey = stage ?? UNKNOWN_STAGE;
    let bucket = this.buckets.get(stageKey);
    if (!bucket) {
      bucket = { stage, grant: null, narration: [], decisions: [], milestones: [] };
      this.buckets.set(stageKey, bucket);
      this.order.push(stageKey);
    }
    return bucket;
  }
}

/**
 * Merge run events + audit events and segment them into ordered rounds:
 *   - setup:  leading `provision` items before the first non-provision item.
 *   - round N: opens at the first non-pr/learn item after setup or a closed
 *     round; a `monitor_verdict` event closes the round (the verdict belongs
 *     to that round).
 *   - wrapup: trailing pr/learn items after the last closed round.
 *   - other:  anything that does not fit (e.g. a non-pr/learn item appearing
 *     after wrap-up has begun) is collected here rather than dropped.
 */
export function segmentRounds(events: RunEvent[], audit: AuditEvent[]): Round[] {
  const items = mergeStreams(events, audit);
  const rounds: Round[] = [];

  let setup: RoundBuilder | null = null;
  let current: RoundBuilder | null = null;
  let wrapup: RoundBuilder | null = null;
  let other: RoundBuilder | null = null;
  let roundCount = 0;
  let inSetup = true;

  const closeCurrent = () => {
    if (current && !current.isEmpty()) rounds.push(current.build(`round-${roundCount}`, `Round ${roundCount}`));
    current = null;
  };

  for (const item of items) {
    // Leading provision items form the setup segment.
    if (inSetup && isProvision(item)) {
      setup ??= new RoundBuilder();
      setup.add(item);
      continue;
    }
    inSetup = false;

    // Once wrap-up has begun, only further pr/learn items extend it; anything
    // else is unsegmentable and collected under "other".
    if (wrapup) {
      if (isWrapup(item)) {
        wrapup.add(item);
      } else {
        other ??= new RoundBuilder();
        other.add(item);
      }
      continue;
    }

    // pr/learn item with no open round begins the wrap-up segment.
    if (!current && isWrapup(item)) {
      wrapup = new RoundBuilder();
      wrapup.add(item);
      continue;
    }

    // Otherwise this item belongs to a round; open one if needed.
    if (!current) {
      current = new RoundBuilder();
      roundCount += 1;
    }
    current.add(item);

    // A verdict closes the current round (it belongs to the round).
    if (isVerdict(item)) closeCurrent();
  }

  // Emit setup at the front and any open builders at the end, in order.
  const result: Round[] = [];
  if (setup && !setup.isEmpty()) result.push(setup.build("setup", "Setup"));
  closeCurrent();
  result.push(...rounds);
  if (wrapup && !wrapup.isEmpty()) result.push(wrapup.build("wrapup", "Wrap-up"));
  if (other && !other.isEmpty()) result.push(other.build("other", "Other"));
  return result;
}
