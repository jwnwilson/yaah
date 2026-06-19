import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { NotificationBell } from "./NotificationBell";

const NOTICE = {
  id: "m1",
  sender_kind: "system",
  sender_agent_id: null,
  recipient_kind: "user",
  recipient_agent_id: null,
  kind: "gate",
  severity: "attention",
  subject: "Plan ready to review",
  body: "Review the plan",
  run_id: "r1",
  work_item_id: null,
  project_id: null,
  read_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

function mockNotices(count: number) {
  server.use(
    http.get("/api/messages/unread-count", () =>
      HttpResponse.json({ success: true, data: { count }, error: null }),
    ),
    http.get("/api/messages", () =>
      HttpResponse.json({
        success: true,
        data: [NOTICE],
        error: null,
        meta: { total: 1, page_size: 100, page_number: 1 },
      }),
    ),
  );
}

function renderBell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationBell", () => {
  it("shows the unread badge count from the messages API", async () => {
    mockNotices(2);
    renderBell();
    expect(await screen.findByLabelText("2 unread notifications")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("opens a dropdown listing notices with a deep link to the run", async () => {
    mockNotices(1);
    renderBell();
    await userEvent.click(await screen.findByLabelText("1 unread notifications"));
    await waitFor(() => expect(screen.getByText("Plan ready to review")).toBeInTheDocument());
    // gate kind surfaces an "Approval needed" emphasis
    expect(screen.getByText("Approval needed")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /plan ready to review/i });
    expect(link).toHaveAttribute("href", "/runs/r1");
  });
});
