import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { ModelsPage } from "./ModelsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><ModelsPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const AGENT = { id: "ag1", team_id: "tm1", role: "engineer", name: "Eng", persona: "",
  model_alias: "sonnet", runtime: "claude_code", purpose: "", system_prompt: "",
  allowed_tools: ["Read"], skill_ids: [], mcp_server_ids: [], secret_ids: [] };

function mockHappyPath() {
  server.use(
    http.get("/api/teams", () =>
      HttpResponse.json({ success: true, data: [{ id: "tm1", owner_id: "u", name: "Default",
        created_at: "2026-06-14T00:00:00Z" }], error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } }),
    ),
    http.get("/api/teams/tm1/agents", () =>
      HttpResponse.json({ success: true, data: [AGENT], error: null,
        meta: { total: 1, page_size: 200, page_number: 1 } }),
    ),
  );
}

test("lists agents for the first team", async () => {
  mockHappyPath();
  renderPage();
  expect(await screen.findByText("Eng")).toBeInTheDocument();
  expect(screen.getByText("sonnet")).toBeInTheDocument();
});

test("edits model_alias via PATCH", async () => {
  mockHappyPath();
  let patched: unknown = null;
  server.use(
    http.patch("/api/agents/ag1", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({ success: true, data: { ...AGENT, model_alias: "opus" }, error: null });
    }),
  );
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: /edit/i }));
  const input = screen.getByLabelText(/model alias/i);
  await userEvent.clear(input);
  await userEvent.type(input, "opus");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(patched).toEqual({ model_alias: "opus", allowed_tools: ["Read"] }));
});
