import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { server } from "@/test/server";
import { NotificationBell } from "./NotificationBell";

const NOTIFICATION = {
  id: "n1",
  category: "review",
  severity: "attention",
  title: "Approval needed",
  body: null,
  run_id: "r1",
  action: { kind: "gate_approval", run_id: "r1" },
  read_at: null,
  resolved_at: null,
};

function mockNotifications(count: number) {
  server.use(
    http.get("/api/notifications/unread-count", () =>
      HttpResponse.json({ success: true, data: { count }, error: null }),
    ),
    http.get("/api/notifications", () =>
      HttpResponse.json({
        success: true,
        data: [NOTIFICATION],
        error: null,
        meta: { total: 1, page_size: 50, page_number: 1 },
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
  it("shows the unread badge count from the API", async () => {
    mockNotifications(2);
    renderBell();
    expect(await screen.findByLabelText("2 unread notifications")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("opens a dropdown listing notifications with a deep link for gate approvals", async () => {
    mockNotifications(1);
    renderBell();
    await userEvent.click(await screen.findByLabelText("1 unread notifications"));
    await waitFor(() => expect(screen.getByText("Approval needed")).toBeInTheDocument());
    const link = screen.getByRole("link", { name: /approval needed/i });
    expect(link).toHaveAttribute("href", "/runs/r1");
  });
});
