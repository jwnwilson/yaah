import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { listAgents, updateAgent } from "./agents";
import { listTeams } from "./teams";

const AGENT = { id: "ag1", team_id: "tm1", role: "engineer", name: "Eng", persona: "",
  model_alias: "sonnet", runtime: "claude_code", purpose: "", system_prompt: "",
  allowed_tools: ["Read"], skill_ids: [], mcp_server_ids: [], secret_ids: [] };

test("listTeams unwraps the envelope", async () => {
  server.use(
    http.get("/api/teams", () =>
      HttpResponse.json({ success: true, data: [{ id: "tm1", owner_id: "u", name: "Default",
        created_at: "2026-06-14T00:00:00Z" }], error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } }),
    ),
  );
  const teams = await listTeams();
  expect(teams[0].name).toBe("Default");
});

test("listAgents returns agents for a team", async () => {
  server.use(
    http.get("/api/teams/tm1/agents", () =>
      HttpResponse.json({ success: true, data: [AGENT], error: null,
        meta: { total: 1, page_size: 100, page_number: 1 } }),
    ),
  );
  const agents = await listAgents("tm1");
  expect(agents[0].model_alias).toBe("sonnet");
});

test("updateAgent PATCHes model_alias", async () => {
  let body: unknown = null;
  server.use(
    http.patch("/api/agents/ag1", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ success: true, data: { ...AGENT, model_alias: "opus" }, error: null });
    }),
  );
  const updated = await updateAgent("ag1", { model_alias: "opus" });
  expect(body).toEqual({ model_alias: "opus" });
  expect(updated.model_alias).toBe("opus");
});
