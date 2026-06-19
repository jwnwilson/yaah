import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as projects from "@/lib/api/projects";
import { Sidebar } from "./Sidebar";

vi.mock("@/lib/api/projects");
vi.mock("@/modules/theme/ThemeToggle", () => ({ ThemeToggle: () => null }));
vi.mock("@/modules/notifications/NotificationBell", () => ({ NotificationBell: () => null }));

function renderSidebar(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Sidebar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Sidebar", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(projects.listProjects).mockResolvedValue([
      { id: "p1", name: "Alpha", repo_url: "r", local_path: null } as never,
      { id: "p2", name: "Beta", repo_url: "r", local_path: null } as never,
    ]);
  });

  it("shows the current project and its Board/Backlog links", async () => {
    renderSidebar("/projects/p1");
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Board" })).toHaveAttribute("href", "/projects/p1");
    expect(screen.getByRole("link", { name: "Backlog" })).toHaveAttribute(
      "href",
      "/projects/p1/backlog",
    );
  });

  it("opens the switcher and lists projects + New project", async () => {
    renderSidebar("/projects/p1");
    await screen.findByText("Alpha");
    await userEvent.click(screen.getByRole("button", { name: /Alpha/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Beta" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /New project/ })).toBeInTheDocument();
  });

  it("renders global nav items", async () => {
    renderSidebar("/");
    expect(await screen.findByRole("link", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Runs" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage" })).toBeInTheDocument();
  });
});
