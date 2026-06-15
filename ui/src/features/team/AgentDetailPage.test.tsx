import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { server } from "@/test/server";
import { AgentDetailPage } from "./AgentDetailPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/team/a-lead"]}>
        <Routes>
          <Route path="/team/:agentId" element={<AgentDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const lead = {
  id: "a-lead", team_id: "tm1", role: "lead", name: "Lead", persona: "",
  model_alias: "lead-model", runtime: "claude_code", purpose: "Coordinates the team",
  system_prompt: "", allowed_tools: [], skill_ids: [], mcp_server_ids: [], secret_ids: [],
};

function msg(over: Record<string, unknown>) {
  return {
    id: "m1", sender_kind: "agent", sender_agent_id: "a-lead", recipient_kind: "agent",
    recipient_agent_id: "a-eng", kind: "dispatch", subject: "", body: "x",
    run_id: null, work_item_id: null, project_id: null, read_at: null,
    created_at: "2026-01-01T00:00:00Z", ...over,
  };
}

test("shows the agent header, output, and switches to inbox", async () => {
  server.use(
    http.get("/api/agents/a-lead", () =>
      HttpResponse.json({ success: true, data: lead, error: null })),
    http.get("/api/messages", ({ request }) => {
      const url = new URL(request.url);
      const data = url.searchParams.get("sender")
        ? [msg({ id: "out1", body: "dispatched the engineer" })]
        : [msg({ id: "in1", recipient_agent_id: "a-lead", body: "engineer reported back" })];
      return HttpResponse.json({ success: true, data, error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } });
    }),
  );

  renderPage();
  expect(await screen.findByRole("heading", { name: "Lead" })).toBeInTheDocument();
  expect(screen.getByText("Coordinates the team")).toBeInTheDocument();
  expect(await screen.findByText("dispatched the engineer")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Inbox" }));
  expect(await screen.findByText("engineer reported back")).toBeInTheDocument();
});
