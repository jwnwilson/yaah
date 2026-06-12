import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import ProjectsPage from "./ProjectsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("lists projects and creates a new one", async () => {
  const projects = [{ id: "p1", owner_id: "dev-user", name: "Alpha", repo_url: "x", local_path: null, team_id: null, autonomy: "gated_all", created_at: "2026-01-01T00:00:00Z" }];
  server.use(
    http.get("/api/projects", () =>
      HttpResponse.json({ success: true, data: projects, error: null, meta: { total: projects.length, page_size: 200, page_number: 1 } }),
    ),
    http.post("/api/projects", async ({ request }) => {
      const body = (await request.json()) as { name: string };
      const created = { id: "p2", owner_id: "dev-user", name: body.name, repo_url: "y", local_path: null, team_id: null, autonomy: "gated_all", created_at: "2026-01-02T00:00:00Z" };
      projects.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
  );

  renderPage();
  expect(await screen.findByText("Alpha")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /new project/i }));
  await userEvent.type(screen.getByLabelText(/name/i), "Beta");
  await userEvent.type(screen.getByLabelText(/repo url/i), "y");
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));

  await waitFor(() => expect(screen.getByText("Beta")).toBeInTheDocument());
});
