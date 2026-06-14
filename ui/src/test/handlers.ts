import { http, HttpResponse } from "msw";

// Per-test overrides use server.use(...). Default: empty list responses.
export const handlers = [
  http.get("/api/projects", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 100, page_number: 1 } }),
  ),
  http.get("/api/notifications/unread-count", () =>
    HttpResponse.json({ success: true, data: { count: 0 }, error: null }),
  ),
  http.get("/api/notifications", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } }),
  ),
  http.get("/api/secrets", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 200, page_number: 1 } }),
  ),
  http.get("/api/skills", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 200, page_number: 1 } }),
  ),
  http.get("/api/mcp-servers", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 200, page_number: 1 } }),
  ),
];
