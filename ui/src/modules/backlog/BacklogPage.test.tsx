import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api/backlog";
import BacklogPage from "./BacklogPage";

vi.mock("@/lib/api/backlog");
vi.mock("@/lib/api/projects", () => ({ updateProject: vi.fn() }));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/projects/p1/backlog"]}>
        <Routes>
          <Route path="/projects/:projectId/backlog" element={<BacklogPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BacklogPage", () => {
  beforeEach(() => {
    vi.mocked(api.getBacklog).mockResolvedValue({
      max_concurrent_runs: 2,
      in_flight: 0,
      queued: 0,
      epics: [
        {
          epic: { id: "e1", title: "Login", kind: "epic" } as never,
          active: false,
          ready_count: 1,
          total_tasks: 3,
          done: 0,
          in_flight_count: 0,
        },
      ],
    });
    vi.mocked(api.activateEpic).mockResolvedValue({ id: "e1", active: true } as never);
  });

  it("shows epic readiness and activates", async () => {
    renderPage();
    expect(await screen.findByText("Login")).toBeInTheDocument();
    expect(screen.getByText(/1 ready \/ 3 tasks/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(api.activateEpic).toHaveBeenCalledWith("p1", "e1"));
  });
});
