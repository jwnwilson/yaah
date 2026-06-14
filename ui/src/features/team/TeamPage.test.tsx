import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { TeamPage } from "./TeamPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TeamPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const team = { id: "tm1", owner_id: "dev-user", name: "Default Team", created_at: "2026-01-01T00:00:00Z" };

function agent(over: Record<string, unknown>) {
  return {
    id: "a1", team_id: "tm1", role: "backend", name: "Engineer", persona: "",
    model_alias: "engineer-model", runtime: "claude_code", purpose: "Implements tickets",
    system_prompt: "", allowed_tools: [], skill_ids: [], mcp_server_ids: [], secret_ids: [],
    ...over,
  };
}

test("renders the team roster with role and model", async () => {
  server.use(
    http.get("/api/teams", () =>
      HttpResponse.json({ success: true, data: [team], error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } }),
    ),
    http.get("/api/teams/tm1/agents", () =>
      HttpResponse.json({ success: true,
        data: [agent({ id: "a1", role: "lead", name: "Lead", model_alias: "lead-model" }),
               agent({ id: "a2", role: "backend", name: "Engineer" })],
        error: null, meta: { total: 2, page_size: 200, page_number: 1 } }),
    ),
  );

  renderPage();
  expect(await screen.findByText("Engineer")).toBeInTheDocument();
  expect(screen.getByText("Lead")).toBeInTheDocument();
  expect(screen.getByText(/engineer-model/)).toBeInTheDocument();
});

test("shows an empty state when there is no team", async () => {
  server.use(
    http.get("/api/teams", () =>
      HttpResponse.json({ success: true, data: [], error: null,
        meta: { total: 0, page_size: 100, page_number: 1 } }),
    ),
  );
  renderPage();
  expect(await screen.findByText(/no team yet/i)).toBeInTheDocument();
});
