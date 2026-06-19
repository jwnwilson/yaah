import { http, HttpResponse } from "msw";

// Per-test overrides use server.use(...). Default: empty list responses.
export const handlers = [
  http.get("/api/projects", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 100, page_number: 1 } }),
  ),
  // Default: a run has no memory proposal unless a test overrides this.
  http.get("/api/runs/:runId/memory", () =>
    HttpResponse.json({ success: true, data: null, error: null }),
  ),
  http.get("/api/messages/unread-count", () =>
    HttpResponse.json({ success: true, data: { count: 0 }, error: null }),
  ),
  http.get("/api/messages", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 100, page_number: 1 } }),
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
  http.get("/api/teams", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 100, page_number: 1 } }),
  ),
  http.get("/api/teams/:teamId/agents", () =>
    HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 200, page_number: 1 } }),
  ),
];
