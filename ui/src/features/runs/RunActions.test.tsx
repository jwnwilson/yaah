import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { RunActions } from "./RunActions";
import type { Run } from "@/lib/api/types";

function run(status: Run["status"]): Run {
  return { id: "r1", owner_id: "u", task_id: "t1", team_id: "tm", status, stage: null, branch: null, pr_url: null, cost_usd: 0, created_at: "x" };
}

function renderActions(r: Run) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RunActions taskId="t1" run={r} />
    </QueryClientProvider>,
  );
}

test("approve and reject show only for awaiting_approval runs", () => {
  const { unmount } = renderActions(run("pending"));
  expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  unmount();
  renderActions(run("awaiting_approval"));
  expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
});

test("cancel calls the cancel endpoint", async () => {
  let cancelled = false;
  server.use(
    http.post("/api/runs/r1/cancel", () => {
      cancelled = true;
      return HttpResponse.json({ success: true, data: run("cancelled"), error: null });
    }),
  );
  renderActions(run("pending"));
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
  await waitFor(() => expect(cancelled).toBe(true));
});
