import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { listAudit } from "./audit";

test("listAudit returns events and meta and forwards filters", async () => {
  let url = "";
  server.use(
    http.get("/api/audit", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        success: true,
        data: [{ id: "a1", run_id: "r1", stage: null, actor: "lead", action: "tool_denied",
          detail: { tool: "Bash" }, created_at: "2026-06-14T00:00:00Z" }],
        error: null,
        meta: { total: 1, page_size: 50, page_number: 1 },
      });
    }),
  );
  const res = await listAudit({ action: "tool_denied", page_number: 1 });
  expect(url).toContain("action=tool_denied");
  expect(res.data[0].action).toBe("tool_denied");
  expect(res.meta?.total).toBe(1);
});
