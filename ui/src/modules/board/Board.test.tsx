import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { server } from "@/test/server";
import { Board } from "./Board";

function renderBoard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Board projectId="p1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders columns and places tasks by status", async () => {
  server.use(
    http.get("/api/projects/p1/work-items", () =>
      HttpResponse.json({
        success: true,
        data: [
          { id: "t1", project_id: "p1", owner_id: "u", kind: "task", parent_id: "f", title: "Build login", body: "", acceptance_criteria: [], status: "ready", created_at: "x", updated_at: "x" },
          { id: "t2", project_id: "p1", owner_id: "u", kind: "task", parent_id: "f", title: "Broken thing", body: "", acceptance_criteria: [], status: "failed", created_at: "x", updated_at: "x" },
        ],
        error: null,
        meta: { total: 2, page_size: 200, page_number: 1 },
      }),
    ),
  );
  renderBoard();
  expect(await screen.findByText("Build login")).toBeInTheDocument();
  expect(screen.getByText("Broken thing")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /attention/i })).toBeInTheDocument();
});
