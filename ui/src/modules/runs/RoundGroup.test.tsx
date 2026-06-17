import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { AuditEvent, RunEvent } from "@/lib/api/types";
import { RoundGroup } from "./RoundGroup";
import type { Round } from "./runTimeline";

function ev(over: Partial<RunEvent> & Pick<RunEvent, "id" | "type">): RunEvent {
  return {
    run_id: "r1",
    stage: "implement",
    message: "",
    created_at: "2026-06-17T00:00:00Z",
    ...over,
  };
}

function aud(over: Partial<AuditEvent> & Pick<AuditEvent, "id" | "action">): AuditEvent {
  return {
    run_id: "r1",
    stage: "implement",
    actor: "lead",
    detail: {},
    created_at: "2026-06-17T00:00:00Z",
    ...over,
  };
}

function renderGroup(round: Round, defaultExpanded = false) {
  return render(
    <MemoryRouter>
      <RoundGroup round={round} defaultExpanded={defaultExpanded} />
    </MemoryRouter>,
  );
}

const baseRound: Round = {
  key: "round-1",
  label: "Round 1",
  stages: [
    {
      stage: "implement",
      grant: aud({ id: "g1", action: "capability_granted", detail: { tools: ["edit", "bash"] } }),
      narration: [ev({ id: "n1", type: "agent_event", message: "writing code" })],
      decisions: [aud({ id: "d1", action: "tool_denied", detail: { tool: "bash", reason: "blocked" } })],
      milestones: [
        ev({ id: "m1", type: "stage_started", message: "implement started" }),
        ev({ id: "m2", type: "agent_dispatched", message: "dispatch backend", agent_id: "ag1" }),
      ],
    },
  ],
};

test("collapsed shows milestones and the milestone count, hiding narration", () => {
  renderGroup(baseRound, false);
  expect(screen.getByText("2 milestones")).toBeInTheDocument();
  expect(screen.getByText("implement started")).toBeInTheDocument();
  expect(screen.queryByText("writing code")).not.toBeInTheDocument();
});

test("expanding reveals the stage grant, narration and tool decisions", () => {
  renderGroup(baseRound, false);
  fireEvent.click(screen.getByRole("button", { expanded: false }));
  expect(screen.getByText(/Capabilities/)).toBeInTheDocument();
  expect(screen.getByText(/edit, bash/)).toBeInTheDocument();
  expect(screen.getByText("writing code")).toBeInTheDocument();
  expect(screen.getByText(/denied bash/)).toBeInTheDocument();
});

test("an agent_dispatched milestone links to the agent route", () => {
  renderGroup(baseRound, false);
  const link = screen.getByRole("link", { name: "dispatch backend" });
  expect(link).toHaveAttribute("href", "/team/ag1");
});

test("an error event renders with danger styling", () => {
  const round: Round = {
    key: "round-1",
    label: "Round 1",
    stages: [
      {
        stage: "verify",
        grant: null,
        narration: [],
        decisions: [],
        milestones: [ev({ id: "x1", type: "error", stage: "verify", message: "boom" })],
      },
    ],
  };
  renderGroup(round, false);
  const row = screen.getByText("boom").closest("div");
  expect(row?.parentElement?.className ?? row?.className).toMatch(/text-danger/);
});

test("defaultExpanded renders the expanded view immediately", () => {
  renderGroup(baseRound, true);
  expect(screen.getByRole("button", { expanded: true })).toBeInTheDocument();
  expect(screen.getByText("writing code")).toBeInTheDocument();
});
