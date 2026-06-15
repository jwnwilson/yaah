import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { workItemKeys } from "@/lib/api/workItems";
import { useSetStatus } from "./useSetStatus";
import type { WorkItem } from "@/lib/api/types";

const PROJECT = "p1";
function task(id: string, status: WorkItem["status"]): WorkItem {
  return { id, project_id: PROJECT, owner_id: "u", kind: "task", parent_id: "f", title: id, body: "", acceptance_criteria: [], status, assignee_agent_id: null, created_at: "x", updated_at: "x" };
}

function makeWrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

test("rolls back the cached status when the API returns 409", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(workItemKeys.list(PROJECT), [task("a", "ready")]);
  server.use(
    http.post("/api/work-items/a/status", () =>
      HttpResponse.json({ success: false, data: null, error: "bad transition" }, { status: 409 }),
    ),
  );

  const { result } = renderHook(() => useSetStatus(PROJECT), { wrapper: makeWrapper(qc) });
  result.current.mutate({ itemId: "a", status: "done" });

  await waitFor(() => expect(result.current.isError).toBe(true));
  const cached = qc.getQueryData<WorkItem[]>(workItemKeys.list(PROJECT))!;
  expect(cached[0].status).toBe("ready"); // rolled back
});
