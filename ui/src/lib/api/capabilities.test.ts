import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { listSecrets, setSecretValue, createSkill, listMcpServers } from "./capabilities";

test("listSecrets unwraps the envelope and never includes a value", async () => {
  server.use(
    http.get("/api/secrets", () =>
      HttpResponse.json({
        success: true,
        data: [{ id: "s1", owner_id: "u", name: "GITHUB_TOKEN", description: "", has_value: true, created_at: "2026-01-01T00:00:00Z" }],
        error: null,
        meta: { total: 1, page_size: 200, page_number: 1 },
      }),
    ),
  );
  const secrets = await listSecrets();
  expect(secrets[0].name).toBe("GITHUB_TOKEN");
  expect(secrets[0].has_value).toBe(true);
  expect("value" in secrets[0]).toBe(false);
});

test("setSecretValue PUTs the value and returns the updated secret", async () => {
  let sentBody: unknown = null;
  server.use(
    http.put("/api/secrets/s1/value", async ({ request }) => {
      sentBody = await request.json();
      return HttpResponse.json({
        success: true,
        data: { id: "s1", owner_id: "u", name: "GITHUB_TOKEN", description: "", has_value: true, created_at: "2026-01-01T00:00:00Z" },
        error: null,
      });
    }),
  );
  const updated = await setSecretValue("s1", "ghp_secret");
  expect(sentBody).toEqual({ value: "ghp_secret" });
  expect(updated.has_value).toBe(true);
});

test("createSkill POSTs to /api/skills", async () => {
  server.use(
    http.post("/api/skills", async ({ request }) => {
      const body = (await request.json()) as { name: string };
      return HttpResponse.json({ success: true, data: { id: "k1", owner_id: "u", name: body.name, description: "", source: "", created_at: "2026-01-01T00:00:00Z" }, error: null }, { status: 201 });
    }),
  );
  const skill = await createSkill({ name: "search" });
  expect(skill.id).toBe("k1");
});

test("listMcpServers returns the registry rows", async () => {
  server.use(
    http.get("/api/mcp-servers", () =>
      HttpResponse.json({ success: true, data: [{ id: "m1", owner_id: "u", name: "github", transport: "stdio", command_or_url: "npx ...", tool_allowlist: ["mcp__github__search"], created_at: "2026-01-01T00:00:00Z" }], error: null, meta: { total: 1, page_size: 200, page_number: 1 } }),
    ),
  );
  const servers = await listMcpServers();
  expect(servers[0].tool_allowlist).toEqual(["mcp__github__search"]);
});
