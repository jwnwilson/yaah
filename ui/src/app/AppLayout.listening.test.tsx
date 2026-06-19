import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import { AppLayout } from "./AppLayout";

const launcher = vi.hoisted(() => ({ listening: false }));

vi.mock("@/modules/chat/ChatLauncherContext", () => ({
  ChatLauncherProvider: ({ children }: { children: ReactNode }) => children,
  useChatLauncher: () => ({
    open: false,
    dictate: false,
    listening: launcher.listening,
    openChat: vi.fn(),
    toggle: vi.fn(),
    close: vi.fn(),
    consumeDictate: vi.fn(),
    setListening: vi.fn(),
  }),
}));
vi.mock("@/modules/projects/useCurrentProject", () => ({ useCurrentProjectId: () => "p1" }));

afterEach(() => {
  launcher.listening = false;
});

function renderLayout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AppLayout />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("shows the Listening… indicator on the global mic while dictating", () => {
  launcher.listening = true;
  renderLayout();
  expect(screen.getByText(/listening…/i)).toBeInTheDocument();
});

test("hides the Listening… indicator when not dictating", () => {
  launcher.listening = false;
  renderLayout();
  expect(screen.queryByText(/listening…/i)).not.toBeInTheDocument();
});
