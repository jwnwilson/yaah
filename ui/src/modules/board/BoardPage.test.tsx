import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { ChatLauncherProvider } from "@/modules/chat/ChatLauncherContext";
import BoardPage from "./BoardPage";

// Keep the chat lightweight: a marker we can assert on without its network deps.
vi.mock("@/modules/chat/ChatRail", () => ({
  ChatRail: () => <div data-testid="chat-rail">chat</div>,
}));

vi.mock("@/modules/backlog/useBacklog", () => ({
  useBacklog: () => ({
    query: { data: undefined, isError: false, error: null },
    activate: { mutate: vi.fn() },
    deactivate: { mutate: vi.fn() },
  }),
}));

vi.mock("@/modules/projects/useProjects", () => ({
  useProjects: () => ({ data: [] }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChatLauncherProvider>
        <MemoryRouter initialEntries={["/projects/p1"]}>
          <Routes>
            <Route path="/projects/:projectId" element={<BoardPage />} />
          </Routes>
        </MemoryRouter>
      </ChatLauncherProvider>
    </QueryClientProvider>,
  );
}

describe("BoardPage team-lead chat toggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("toggles ChatRail via the shared launcher button", async () => {
    renderPage();

    // closed by default
    expect(screen.queryByTestId("chat-rail")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Team lead" })).toBeInTheDocument();

    // open
    await userEvent.click(screen.getByRole("button", { name: "Team lead" }));
    expect(screen.getByTestId("chat-rail")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide chat" })).toBeInTheDocument();

    // close
    await userEvent.click(screen.getByRole("button", { name: "Hide chat" }));
    expect(screen.queryByTestId("chat-rail")).not.toBeInTheDocument();
  });
});
