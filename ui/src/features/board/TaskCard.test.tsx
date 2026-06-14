import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DndContext } from "@dnd-kit/core";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { TaskCard } from "./TaskCard";
import type { WorkItem } from "../../lib/api/types";

const eng = {
  id: "a-eng", team_id: "tm1", role: "backend", name: "Engineer", persona: "",
  model_alias: "m", runtime: "claude_code", purpose: "", system_prompt: "",
  allowed_tools: [], skill_ids: [], mcp_server_ids: [], secret_ids: [],
};

function item(over: Partial<WorkItem> = {}): WorkItem {
  return {
    id: "t1", project_id: "p1", owner_id: "u", kind: "task", parent_id: "f1",
    title: "Build it", body: "", acceptance_criteria: [], status: "ready",
    assignee_agent_id: null, created_at: "x", updated_at: "x", ...over,
  };
}

function renderCard(it: WorkItem) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  server.use(
    http.get("/api/teams", () =>
      HttpResponse.json({ success: true, data: [{ id: "tm1", owner_id: "u", name: "T", created_at: "x" }],
        error: null, meta: { total: 1, page_size: 100, page_number: 1 } })),
    http.get("/api/teams/tm1/agents", () =>
      HttpResponse.json({ success: true, data: [eng], error: null,
        meta: { total: 1, page_size: 200, page_number: 1 } })),
  );
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <DndContext>
          <Routes>
            <Route path="/projects/:projectId" element={<TaskCard item={it} onOpen={() => {}} />} />
          </Routes>
        </DndContext>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("shows the assignee avatar when assigned", async () => {
  renderCard(item({ assignee_agent_id: "a-eng" }));
  expect(await screen.findByLabelText("Assignee Engineer")).toBeInTheDocument();
});

test("assigning via the picker PATCHes the work item", async () => {
  let body: unknown = null;
  server.use(
    http.patch("/api/work-items/:id", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ success: true, data: item({ assignee_agent_id: "a-eng" }), error: null });
    }),
  );
  renderCard(item());
  const select = await screen.findByLabelText("Assignee");
  await userEvent.selectOptions(select, "a-eng");
  await waitFor(() => expect(body).toEqual({ assignee_agent_id: "a-eng" }));
});
