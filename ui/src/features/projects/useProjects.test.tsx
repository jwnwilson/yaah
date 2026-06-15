import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { useProjects } from "./useProjects";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("useProjects returns the project list", async () => {
  server.use(
    http.get("/api/projects", () =>
      HttpResponse.json({
        success: true,
        data: [{ id: "p1", owner_id: "dev-user", name: "Alpha", repo_url: "x", local_path: null, team_id: null, autonomy: "gated_all", created_at: "2026-01-01T00:00:00Z" }],
        error: null,
        meta: { total: 1, page_size: 100, page_number: 1 },
      }),
    ),
  );
  const { result } = renderHook(() => useProjects(), { wrapper });
  await waitFor(() => expect(result.current.data).toHaveLength(1));
  expect(result.current.data![0].name).toBe("Alpha");
});
