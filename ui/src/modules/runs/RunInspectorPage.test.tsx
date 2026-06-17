import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { server } from "@/test/server";
import { RunInspectorPage } from "./RunInspectorPage";

function ok(data: unknown, meta?: unknown) {
  return HttpResponse.json({ success: true, data, error: null, meta });
}

const PAGE_META = { total: 0, page_size: 200, page_number: 1 };

const run = {
  id: "run1",
  owner_id: "dev-user",
  task_id: "task1",
  team_id: "tm1",
  status: "done",
  stage: "learn",
  branch: "feat/x",
  pr_url: "https://example.com/pr/1",
  cost_usd: 1.23,
  input_tokens: 1000,
  output_tokens: 200,
  cache_read_tokens: 0,
  cache_creation_tokens: 0,
  created_at: "2026-06-17T00:00:00Z",
};

function setup({
  runData = run,
  events = [] as unknown[],
  usage = null as unknown,
  audit = [] as unknown[],
}: {
  runData?: unknown;
  events?: unknown[];
  usage?: unknown;
  audit?: unknown[];
} = {}) {
  server.use(
    http.get("/api/runs/run1", () => ok(runData)),
    http.get("/api/runs/run1/events", () => ok(events, PAGE_META)),
    http.get("/api/runs/run1/usage", () => ok(usage)),
    http.get("/api/runs/run1/audit", () => ok(audit, PAGE_META)),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/runs/run1"]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunInspectorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders the header with status, stage and total cost", async () => {
  setup();
  expect(await screen.findByText("done")).toBeInTheDocument();
  expect(screen.getByText("learn")).toBeInTheDocument();
  expect(screen.getByText("$1.23")).toBeInTheDocument();
  expect(screen.getByText(/1,000 in/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "PR" })).toHaveAttribute("href", "https://example.com/pr/1");
});

test("renders the cost-by-stage table from usage", async () => {
  setup({
    usage: {
      input_tokens: 0,
      output_tokens: 0,
      cache_read_tokens: 0,
      cache_creation_tokens: 0,
      cost_usd: 0,
      total_tokens: 0,
      breakdown: [
        { stage: "plan", model_id: "m", agent_role: "lead", input_tokens: 100, output_tokens: 10, cost_usd: 0.5 },
        { stage: "implement", model_id: "m", agent_role: "backend", input_tokens: 200, output_tokens: 20, cost_usd: 0.7 },
      ],
    },
  });
  expect(await screen.findByText("done")).toBeInTheDocument();
  expect(screen.getByText("plan")).toBeInTheDocument();
  expect(screen.getByText("implement")).toBeInTheDocument();
  expect(screen.getByText("Total")).toBeInTheDocument();
  // grand total cost row
  expect(screen.getByText("$1.20")).toBeInTheDocument();
});

test("renders round groups segmented from events", async () => {
  setup({
    events: [
      { id: "e1", run_id: "run1", stage: "plan", type: "stage_started", message: "lead plans", created_at: "2026-06-17T00:00:01Z" },
      { id: "e2", run_id: "run1", stage: "verify", type: "monitor_verdict", message: "accepted", created_at: "2026-06-17T00:00:02Z" },
    ],
  });
  expect(await screen.findByText("Round 1")).toBeInTheDocument();
  expect(screen.getByText("lead plans")).toBeInTheDocument();
});

test("shows an empty state when there are no rounds yet", async () => {
  setup({ events: [] });
  expect(await screen.findByText(/waiting for the first round/i)).toBeInTheDocument();
});
