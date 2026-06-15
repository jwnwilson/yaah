import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { MemoryPage } from "./MemoryPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><MemoryPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const PROPOSAL = { id: "m1", run_id: "r1", project_id: "p1", branch: "b", diff: "+new",
  files: ["CLAUDE.md"], status: "applied", pr_url: null, resolved_at: null,
  created_at: "2026-06-14T00:00:00Z" };

test("renders proposals and expands diff", async () => {
  server.use(
    http.get("/api/memory-proposals", () =>
      HttpResponse.json({ success: true, data: [PROPOSAL], error: null,
        meta: { total: 1, page_size: 50, page_number: 1 } }),
    ),
  );
  renderPage();
  expect(await screen.findByText("CLAUDE.md")).toBeInTheDocument();
  expect(screen.getByText("applied")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(screen.getByText("+new")).toBeInTheDocument();
});

test("filters by status", async () => {
  let url = "";
  server.use(
    http.get("/api/memory-proposals", ({ request }) => {
      url = request.url;
      return HttpResponse.json({ success: true, data: [], error: null,
        meta: { total: 0, page_size: 50, page_number: 1 } });
    }),
  );
  renderPage();
  await userEvent.selectOptions(await screen.findByLabelText(/status/i), "rejected");
  expect(url).toContain("status=rejected");
  expect(await screen.findByText(/no memory proposals/i)).toBeInTheDocument();
});
