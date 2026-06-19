import { describe, expect, it } from "vitest";
import type { BacklogView } from "@/lib/api/backlog";
import type { WorkItem } from "@/lib/api/types";
import { deriveBoard } from "./boardData";

function wi(over: Partial<WorkItem>): WorkItem {
  return {
    id: "x", project_id: "p", owner_id: "u", kind: "task", parent_id: null,
    title: "t", body: "", acceptance_criteria: [], status: "ready",
    assignee_agent_id: null, active: false, position: 0,
    created_at: "x", updated_at: "x", ...over,
  } as WorkItem;
}

const view: BacklogView = {
  max_concurrent_runs: 2,
  in_flight: 0,
  queued: 0,
  epics: [
    {
      epic: wi({ id: "e1", kind: "epic", title: "Active epic", active: true }),
      active: true,
      ready_count: 0, total_tasks: 0, done: 0, in_flight_count: 0,
      tasks: [wi({ id: "t-e1", parent_id: "e1" })],
      features: [
        {
          feature: wi({ id: "f1", kind: "feature", parent_id: "e1", title: "F1" }),
          tasks: [wi({ id: "t-f1", parent_id: "f1", assignee_agent_id: "a1" })],
        },
      ],
    },
    {
      epic: wi({ id: "e2", kind: "epic", title: "Inactive epic", active: false }),
      active: false,
      ready_count: 0, total_tasks: 0, done: 0, in_flight_count: 0,
      tasks: [wi({ id: "t-e2", parent_id: "e2" })],
      features: [
        {
          feature: wi({ id: "f2", kind: "feature", parent_id: "e2", title: "Active feature", active: true }),
          tasks: [wi({ id: "t-f2", parent_id: "f2" })],
        },
        {
          feature: wi({ id: "f3", kind: "feature", parent_id: "e2", title: "Inactive feature" }),
          tasks: [wi({ id: "t-f3", parent_id: "f3" })],
        },
      ],
    },
  ],
};

describe("deriveBoard", () => {
  it("includes tasks under active epics and active features (union), excludes the rest", () => {
    const b = deriveBoard(view);
    const ids = b.tasks.map((t) => t.id).sort();
    // t-e1 (active epic direct), t-f1 (feature of active epic), t-f2 (independently active feature)
    expect(ids).toEqual(["t-e1", "t-f1", "t-f2"]);
    // t-e2 (inactive epic direct) and t-f3 (inactive feature) excluded
    expect(ids).not.toContain("t-e2");
    expect(ids).not.toContain("t-f3");
  });

  it("offers only active epics and board features as filter options", () => {
    const b = deriveBoard(view);
    expect(b.epicOptions.map((e) => e.id)).toEqual(["e1"]);
    expect(b.featureOptions.map((f) => f.id).sort()).toEqual(["f1", "f2"]);
    expect(b.taskEpicId["t-f1"]).toBe("e1");
  });

  it("returns empty board for no data", () => {
    expect(deriveBoard(undefined).tasks).toEqual([]);
  });
});
