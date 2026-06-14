import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { getUsage } from "./usage";

test("getUsage passes group_by and project_id as query params and unwraps totals", async () => {
  let url = "";
  server.use(
    http.get("/api/usage", ({ request }) => {
      url = request.url;
      return HttpResponse.json({
        success: true,
        data: { totals: { input_tokens: 10, output_tokens: 2, cache_read_tokens: 0,
          cache_creation_tokens: 0, cost_usd: 0.1, total_tokens: 12 },
          group_by: "model", groups: { m1: { input_tokens: 10, output_tokens: 2,
            cache_read_tokens: 0, cache_creation_tokens: 0, cost_usd: 0.1, total_tokens: 12 } } },
        error: null,
      });
    }),
  );
  const rollup = await getUsage({ group_by: "model", project_id: "p1" });
  expect(url).toContain("group_by=model");
  expect(url).toContain("project_id=p1");
  expect(rollup.totals.total_tokens).toBe(12);
  expect(rollup.groups?.m1.input_tokens).toBe(10);
});
