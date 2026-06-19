import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as backlog from "@/lib/api/backlog";
import type { WorkItem } from "@/lib/api/types";
import * as workItems from "@/lib/api/workItems";
import BacklogPage from "./BacklogPage";

vi.mock("@/lib/api/backlog");
vi.mock("@/lib/api/workItems");
vi.mock("@/lib/api/projects", () => ({ updateProject: vi.fn() }));

function wi(over: Record<string, unknown>): WorkItem {
  return {
    id: "x", project_id: "p1", owner_id: "u", kind: "task", parent_id: null,
    title: "t", body: "", acceptance_criteria: [], status: "draft",
    assignee_agent_id: null, active: false, position: 0,
    created_at: "x", updated_at: "x", ...over,
  } as WorkItem;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/projects/p1/backlog"]}>
        <Routes>
          <Route path="/projects/:projectId/backlog" element={<BacklogPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BacklogPage", () => {
  beforeEach(() => {
    vi.mocked(backlog.getBacklog).mockResolvedValue({
      max_concurrent_runs: 2,
      in_flight: 0,
      queued: 1,
      epics: [
        {
          epic: wi({ id: "e1", kind: "epic", title: "Auth", active: false }),
          active: false,
          ready_count: 1,
          total_tasks: 1,
          done: 0,
          in_flight_count: 0,
          features: [
            {
              feature: wi({ id: "f1", kind: "feature", parent_id: "e1", title: "Login flow" }),
              tasks: [wi({ id: "t1", parent_id: "f1", title: "Build form", status: "ready" })],
            },
          ],
          tasks: [],
        },
      ],
    });
    vi.mocked(backlog.activateItem).mockResolvedValue(wi({ id: "e1", active: true }) as never);
    vi.mocked(workItems.createWorkItem).mockResolvedValue(wi({ id: "new" }) as never);
  });

  it("renders the epic tree (epic + nested feature + task on expand)", async () => {
    renderPage();
    expect(await screen.findByText("Auth")).toBeInTheDocument();
    expect(screen.getByText(/running 0 \/ 2 · queued 1/)).toBeInTheDocument();
    // inactive epics start collapsed; expand to reveal the nested feature + task
    await userEvent.click(screen.getByRole("button", { name: "expand" }));
    expect(screen.getByText("Login flow")).toBeInTheDocument();
    expect(screen.getByText("Build form")).toBeInTheDocument();
  });

  it("activates an epic", async () => {
    renderPage();
    await screen.findByText("Auth");
    await userEvent.click(screen.getByRole("button", { name: "activate" }));
    await waitFor(() => expect(backlog.activateItem).toHaveBeenCalledWith("p1", "e1"));
  });

  it("creates an epic via inline add", async () => {
    renderPage();
    await screen.findByText("Auth");
    await userEvent.click(screen.getByRole("button", { name: "+ epic" }));
    await userEvent.type(screen.getByPlaceholderText("epic"), "Billing{Enter}");
    await waitFor(() =>
      expect(workItems.createWorkItem).toHaveBeenCalledWith("p1", { kind: "epic", title: "Billing" }),
    );
  });
});

describe("BacklogPage feature details", () => {
  beforeEach(() => {
    vi.mocked(backlog.getBacklog).mockResolvedValue({
      max_concurrent_runs: 2,
      in_flight: 0,
      queued: 0,
      epics: [
        {
          epic: wi({ id: "e1", kind: "epic", title: "Auth", active: false }),
          active: false,
          ready_count: 0,
          total_tasks: 0,
          done: 0,
          in_flight_count: 0,
          features: [
            { feature: wi({ id: "f1", kind: "feature", parent_id: "e1", title: "Login flow" }), tasks: [] },
          ],
          tasks: [],
        },
      ],
    });
  });

  it("clicking a feature opens the details panel in the backlog", async () => {
    renderPage();
    await screen.findByText("Auth");
    await userEvent.click(screen.getByRole("button", { name: "expand" }));
    await userEvent.click(screen.getByText("Login flow"));
    // the DetailPeek side panel mounts (its close control appears)
    expect(await screen.findByRole("button", { name: "close" })).toBeInTheDocument();
  });
});

function epicEntry(over: {
  id: string;
  title: string;
  active?: boolean;
  features?: backlog.BacklogFeature[];
}): backlog.BacklogEpic {
  return {
    epic: wi({ id: over.id, kind: "epic", title: over.title, active: over.active ?? false }),
    active: over.active ?? false,
    ready_count: 0,
    total_tasks: 0,
    done: 0,
    in_flight_count: 0,
    features: over.features ?? [],
    tasks: [],
  };
}

function mockBacklog(epics: backlog.BacklogEpic[]) {
  vi.mocked(backlog.getBacklog).mockResolvedValue({
    max_concurrent_runs: 2,
    in_flight: 0,
    queued: 0,
    epics,
  });
}

describe("BacklogPage active-work divider", () => {
  it("separates active-work epics from the rest, active ones first", async () => {
    mockBacklog([
      epicEntry({ id: "e1", title: "Backlog epic" }),
      epicEntry({ id: "e2", title: "Active epic", active: true }),
    ]);
    renderPage();

    await screen.findByText("Active epic");
    expect(screen.getByRole("separator", { name: "backlog" })).toBeInTheDocument();
    // active-work epics render above the divider, the rest below
    const active = screen.getByText("Active epic");
    const inactive = screen.getByText("Backlog epic");
    expect(active.compareDocumentPosition(inactive)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("treats an epic with an active feature as active work", async () => {
    mockBacklog([
      epicEntry({ id: "e1", title: "Plain epic" }),
      epicEntry({
        id: "e2",
        title: "Epic with active feature",
        features: [
          {
            feature: wi({ id: "f1", kind: "feature", parent_id: "e2", title: "Live feature", active: true }),
            tasks: [],
          },
        ],
      }),
    ]);
    renderPage();

    await screen.findByText("Epic with active feature");
    expect(screen.getByRole("separator", { name: "backlog" })).toBeInTheDocument();
    const activeWork = screen.getByText("Epic with active feature");
    const plain = screen.getByText("Plain epic");
    expect(activeWork.compareDocumentPosition(plain)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("omits the divider when no epic is active work", async () => {
    mockBacklog([
      epicEntry({ id: "e1", title: "One" }),
      epicEntry({ id: "e2", title: "Two" }),
    ]);
    renderPage();

    await screen.findByText("One");
    expect(screen.queryByRole("separator", { name: "backlog" })).not.toBeInTheDocument();
  });

  it("omits the divider when every epic is active work", async () => {
    mockBacklog([
      epicEntry({ id: "e1", title: "One", active: true }),
      epicEntry({ id: "e2", title: "Two", active: true }),
    ]);
    renderPage();

    await screen.findByText("One");
    expect(screen.queryByRole("separator", { name: "backlog" })).not.toBeInTheDocument();
  });
});
