import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { listMemoryProposals } from "./memory";

test("listMemoryProposals returns proposals + meta and forwards filters", async () => {
  let url = "";
  server.use(
    http.get("/api/memory-proposals", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        success: true,
        data: [{ id: "m1", run_id: "r1", project_id: "p1", branch: "b", diff: "d",
          files: ["CLAUDE.md"], status: "applied", pr_url: null, resolved_at: null,
          created_at: "2026-06-14T00:00:00Z" }],
        error: null,
        meta: { total: 1, page_size: 50, page_number: 1 },
      });
    }),
  );
  const res = await listMemoryProposals({ status: "applied" });
  expect(url).toContain("status=applied");
  expect(res.data[0].status).toBe("applied");
  expect(res.meta?.total).toBe(1);
});
