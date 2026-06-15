import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { AuditPage } from "./AuditPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><AuditPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders events and filters by action", async () => {
  server.use(
    http.get("/api/audit", ({ request }) => {
      const action = new URL(request.url).searchParams.get("action");
      const all = [
        { id: "a1", run_id: "r1", stage: null, actor: "lead", action: "tool_allowed",
          detail: { tool: "Read" }, created_at: "2026-06-14T00:00:00Z" },
        { id: "a2", run_id: "r1", stage: null, actor: "lead", action: "tool_denied",
          detail: { tool: "Bash" }, created_at: "2026-06-14T00:01:00Z" },
      ];
      const data = action ? all.filter((e) => e.action === action) : all;
      return HttpResponse.json({ success: true, data, error: null,
        meta: { total: data.length, page_size: 50, page_number: 1 } });
    }),
  );
  renderPage();
  expect(await screen.findByText("Read")).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText(/action/i), "tool_denied");
  expect(await screen.findByText("Bash")).toBeInTheDocument();
  expect(screen.queryByText("Read")).not.toBeInTheDocument();
});

test("shows empty state", async () => {
  server.use(
    http.get("/api/audit", () =>
      HttpResponse.json({ success: true, data: [], error: null,
        meta: { total: 0, page_size: 50, page_number: 1 } }),
    ),
  );
  renderPage();
  expect(await screen.findByText(/no audit events/i)).toBeInTheDocument();
});
