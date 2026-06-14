import { expect, test } from "vitest";
import { BOARD_COLUMNS, columnForStatus, groupByColumn, ATTENTION } from "./columns";
import type { WorkItem } from "../../lib/api/types";

function task(id: string, status: WorkItem["status"]): WorkItem {
  return {
    id, project_id: "p", owner_id: "u", kind: "task", parent_id: "f",
    title: id, body: "", acceptance_criteria: [], status, assignee_agent_id: null,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };
}

test("there are 7 flow columns plus the attention column", () => {
  expect(BOARD_COLUMNS).toHaveLength(8);
  expect(BOARD_COLUMNS[BOARD_COLUMNS.length - 1].id).toBe(ATTENTION);
});

test("blocked and failed map to the attention column", () => {
  expect(columnForStatus("blocked")).toBe(ATTENTION);
  expect(columnForStatus("failed")).toBe(ATTENTION);
});

test("flow statuses map to their own column", () => {
  expect(columnForStatus("ready")).toBe("ready");
  expect(columnForStatus("in_progress")).toBe("in_progress");
});

test("groupByColumn buckets tasks under the right columns", () => {
  const grouped = groupByColumn([task("a", "ready"), task("b", "failed"), task("c", "blocked")]);
  expect(grouped.ready.map((t) => t.id)).toEqual(["a"]);
  expect(grouped[ATTENTION].map((t) => t.id)).toEqual(["b", "c"]);
});
