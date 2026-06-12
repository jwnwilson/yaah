import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { TicketPanel } from "./TicketPanel";

const item = { id: "t1", project_id: "p1", owner_id: "u", kind: "task", parent_id: "f", title: "Build login", body: "do it", acceptance_criteria: ["AC1"], status: "ready", created_at: "x", updated_at: "x" };

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TicketPanel projectId="p1" itemId="t1" onClose={() => {}} />
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
    http.get("/api/work-items/t1/runs", () => HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 100, page_number: 1 } })),
  );

  renderPanel();
  expect(await screen.findByDisplayValue("Build login")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /add criterion/i }));
  const inputs = screen.getAllByPlaceholderText(/criterion/i);
  await userEvent.type(inputs[inputs.length - 1], "AC2");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(current.acceptance_criteria).toContain("AC2"));
});
