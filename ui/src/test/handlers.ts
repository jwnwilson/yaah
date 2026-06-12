import { http, HttpResponse } from "msw";

// Per-test overrides use server.use(...). Default: empty list responses.
export const handlers = [
  http.get("/api/projects", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 100, page_number: 1 } }),
  ),
];
