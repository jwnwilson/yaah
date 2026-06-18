import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { server } from "@/test/server";
import { TicketPanel } from "./TicketPanel";

const item = { id: "t1", project_id: "p1", owner_id: "u", kind: "task", parent_id: "f", title: "Build login", body: "do it", acceptance_criteria: ["AC1"], status: "ready", created_at: "x", updated_at: "x" };

function runsResponse(runs: unknown[]) {
  return HttpResponse.json({
    success: true,
    data: runs,
    error: null,
    meta: { total: runs.length, page_size: 100, page_number: 1 },
  });
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TicketPanel projectId="p1" itemId="t1" onClose={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("shows the ticket and saves an edited acceptance criterion", async () => {
  let current = { ...item };
  server.use(
    http.get("/api/work-items/t1", () => HttpResponse.json({ success: true, data: current, error: null })),
    http.patch("/api/work-items/t1", async ({ request }) => {
      const body = (await request.json()) as { acceptance_criteria?: string[] };
      current = { ...current, ...body };
      return HttpResponse.json({ success: true, data: current, error: null });
    }),
    http.get("/api/work-items/t1/runs", () => runsResponse([])),
    http.get("/api/work-items/:id/attachments", () => HttpResponse.json({ success: true, data: [], error: null })),
  );

  renderPanel();
  expect(await screen.findByDisplayValue("Build login")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /add criterion/i }));
  const inputs = screen.getAllByPlaceholderText(/criterion/i);
  await userEvent.type(inputs[inputs.length - 1], "AC2");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(current.acceptance_criteria).toContain("AC2"));
});

test("shows a top View run link pointing at the latest run when runs exist", async () => {
  server.use(
    http.get("/api/work-items/t1", () => HttpResponse.json({ success: true, data: item, error: null })),
    http.get("/api/work-items/:id/attachments", () => HttpResponse.json({ success: true, data: [], error: null })),
    http.get("/api/work-items/t1/runs", () => runsResponse([{ id: "run9", task_id: "t1", status: "running" }])),
  );

  renderPanel();
  const link = await screen.findByRole("link", { name: /view run →/i });
  expect(link).toHaveAttribute("href", "/runs/run9");
});

test("hides the top View run link when the task has no runs", async () => {
  server.use(
    http.get("/api/work-items/t1", () => HttpResponse.json({ success: true, data: item, error: null })),
    http.get("/api/work-items/:id/attachments", () => HttpResponse.json({ success: true, data: [], error: null })),
    http.get("/api/work-items/t1/runs", () => runsResponse([])),
  );

  renderPanel();
  expect(await screen.findByDisplayValue("Build login")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /view run/i })).toBeNull();
});
