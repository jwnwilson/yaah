import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { ChatRail } from "./ChatRail";

function renderRail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChatRail projectId="p1" />
    </QueryClientProvider>,
  );
}

test("sends a message and shows the assistant reply", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
    http.post("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, error: null, data: {
        session_id: "s1", reply: "Drafted an epic", created_items: [] } })),
  );
  renderRail();
  await userEvent.type(screen.getByPlaceholderText(/message the team lead/i), "build login");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  await waitFor(() => expect(screen.getByText("Drafted an epic")).toBeInTheDocument());
});
