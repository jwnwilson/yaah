import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { InboxPage } from "./InboxPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <InboxPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const team = { id: "tm1", owner_id: "dev-user", name: "T", created_at: "2026-01-01T00:00:00Z" };
const eng = {
  id: "a-eng", team_id: "tm1", role: "backend", name: "Engineer", persona: "",
  model_alias: "m", runtime: "claude_code", purpose: "", system_prompt: "",
  allowed_tools: [], skill_ids: [], mcp_server_ids: [], secret_ids: [],
};

function msg(over: Record<string, unknown>) {
  return {
    id: "m1", sender_kind: "system", sender_agent_id: null, recipient_kind: "user",
    recipient_agent_id: null, kind: "chat", subject: "", body: "hello you",
    run_id: null, work_item_id: null, project_id: null, read_at: null,
    created_at: "2026-01-01T00:00:00Z", ...over,
  };
}

function baseHandlers() {
  return [
    http.get("/api/teams", () =>
      HttpResponse.json({ success: true, data: [team], error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } })),
    http.get("/api/teams/tm1/agents", () =>
      HttpResponse.json({ success: true, data: [eng], error: null,
        meta: { total: 1, page_size: 200, page_number: 1 } })),
  ];
}

test("shows the Me mailbox then switches to an agent mailbox", async () => {
  server.use(
    ...baseHandlers(),
    http.get("/api/messages", ({ request }) => {
      const box = new URL(request.url).searchParams.get("box");
      const data =
        box === "a-eng"
          ? [msg({ id: "m2", recipient_kind: "agent", recipient_agent_id: "a-eng",
                   sender_kind: "agent", sender_agent_id: "a-eng", body: "agent note" })]
          : [msg({ body: "hello you" })];
      return HttpResponse.json({ success: true, data, error: null,
        meta: { total: data.length, page_size: 100, page_number: 1 } });
    }),
  );

  renderPage();
  expect(await screen.findByText("hello you")).toBeInTheDocument();
  await userEvent.click(await screen.findByRole("button", { name: /Engineer/ }));
  expect(await screen.findByText("agent note")).toBeInTheDocument();
});

test("marks an unread message read on click", async () => {
  let patched = "";
  server.use(
    ...baseHandlers(),
    http.get("/api/messages", () =>
      HttpResponse.json({ success: true, data: [msg({ id: "m9", body: "tap me" })],
        error: null, meta: { total: 1, page_size: 100, page_number: 1 } })),
    http.patch("/api/messages/:id", ({ params }) => {
      patched = params.id as string;
      return HttpResponse.json({ success: true, data: msg({ id: "m9", read_at: "x" }), error: null });
    }),
  );

  renderPage();
  await userEvent.click(await screen.findByText("tap me"));
  await waitFor(() => expect(patched).toBe("m9"));
});
