import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { server } from "@/test/server";
import { useChat } from "./useChat";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("loads the latest session's messages on open", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, error: null,
        data: [{ id: "s1", project_id: "p1", epic_id: null, created_at: "t" }],
        meta: { total: 1, page_size: 50, page_number: 1 } })),
    http.get("/api/chat/s1/messages", () =>
      HttpResponse.json({ success: true, error: null,
        data: [{ id: "m1", role: "assistant", content: "Welcome back" }],
        meta: { total: 1, page_size: 200, page_number: 1 } })),
  );
  const { result } = renderHook(() => useChat("p1"), { wrapper });
  await waitFor(() => expect(result.current.messages).toHaveLength(1));
  expect(result.current.messages[0].body).toBe("Welcome back");
});
