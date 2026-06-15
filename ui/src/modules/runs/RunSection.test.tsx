import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { Run, WorkItemStatus } from "@/lib/api/types";
import { server } from "@/test/server";
import { RunSection } from "./RunSection";

function renderSection(taskStatus: WorkItemStatus = "ready") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RunSection projectId="p1" taskId="t1" taskStatus={taskStatus} />
    </QueryClientProvider>,
  );
}

test("lists runs and starts a new one", async () => {
  const runs: Run[] = [];
  server.use(
    http.get("/api/work-items/t1/runs", () =>
      HttpResponse.json({ success: true, data: runs, error: null, meta: { total: runs.length, page_size: 100, page_number: 1 } }),
    ),
    http.post("/api/work-items/t1/runs", () => {
      const run: Run = { id: "r1", owner_id: "u", task_id: "t1", team_id: "tm", status: "pending", stage: null, branch: null, pr_url: null, cost_usd: 0, created_at: "x" };
      runs.push(run);
      return HttpResponse.json({ success: true, data: run, error: null }, { status: 201 });
    }),
  );

  renderSection();
  await userEvent.click(await screen.findByRole("button", { name: /^run$/i }));
  await waitFor(() => expect(screen.getByText(/pending/i)).toBeInTheDocument());
});
