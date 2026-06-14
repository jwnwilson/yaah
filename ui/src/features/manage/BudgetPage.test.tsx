import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { BudgetPage } from "./BudgetPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><BudgetPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const TOTALS = { input_tokens: 100, output_tokens: 10, cache_read_tokens: 0,
  cache_creation_tokens: 0, cost_usd: 0.5, total_tokens: 110 };

test("renders totals and switches group-by", async () => {
  server.use(
    http.get("/api/usage", ({ request }) => {
      const group = new URL(request.url).searchParams.get("group_by");
      return HttpResponse.json({
        success: true,
        data: group
          ? { totals: TOTALS, group_by: group, groups: { m1: TOTALS } }
          : { totals: TOTALS },
        error: null,
      });
    }),
  );
  renderPage();
  expect(await screen.findByText(/\$0\.50/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /model/i }));
  expect(await screen.findByText("m1")).toBeInTheDocument();
});

test("shows error state", async () => {
  server.use(
    http.get("/api/usage", () =>
      HttpResponse.json({ success: false, data: null, error: "boom" }, { status: 500 }),
    ),
  );
  renderPage();
  expect(await screen.findByText(/boom/i)).toBeInTheDocument();
});
