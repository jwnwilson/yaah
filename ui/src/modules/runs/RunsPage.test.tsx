import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { RunListItem } from "@/lib/api/types";
import { RunsPage } from "./RunsPage";

const mockUseAllRuns = vi.fn();
vi.mock("./useAllRuns", () => ({
  useAllRuns: () => mockUseAllRuns(),
}));

function makeRun(over: Partial<RunListItem> = {}): RunListItem {
  return {
    id: "run123",
    owner_id: "dev-user",
    task_id: "task1",
    team_id: "team1",
    status: "done",
    stage: "verify",
    branch: null,
    pr_url: null,
    cost_usd: 1.234,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_creation_tokens: 0,
    created_at: new Date().toISOString(),
    task_title: "Build the thing",
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <RunsPage />
    </MemoryRouter>,
  );
}

describe("RunsPage", () => {
  it("renders a row per run with task title, status, and a link to the inspector", () => {
    mockUseAllRuns.mockReturnValue({ data: [makeRun()], isLoading: false });
    renderPage();
    expect(screen.getByText("Build the thing")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Build the thing/ });
    expect(link).toHaveAttribute("href", "/runs/run123");
    expect(screen.getByText("$1.23")).toBeInTheDocument();
  });

  it("falls back to task_id when task_title is null", () => {
    mockUseAllRuns.mockReturnValue({
      data: [makeRun({ task_title: null, task_id: "orphan" })],
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText("orphan")).toBeInTheDocument();
  });

  it("shows an empty state when there are no runs", () => {
    mockUseAllRuns.mockReturnValue({ data: [], isLoading: false });
    renderPage();
    expect(screen.getByText(/no runs/i)).toBeInTheDocument();
  });

  it("shows a spinner while loading", () => {
    mockUseAllRuns.mockReturnValue({ data: undefined, isLoading: true });
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
