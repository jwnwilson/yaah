import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, RouterProvider, createMemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { AppLayout } from "./AppLayout";
import { routes } from "./router";

const navigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => navigate };
});
vi.mock("@/modules/projects/useCurrentProject", () => ({
  useCurrentProjectId: () => "proj-7",
}));

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

test("header shows nav + bell, and Manage routes to the secrets screen", async () => {
  renderAt("/");
  expect(screen.getByRole("link", { name: /projects/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /manage/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/unread notifications/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("link", { name: /manage/i }));
  expect(await screen.findByRole("heading", { name: /secrets/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /mcp servers/i })).toBeInTheDocument();
});

test("the top-right mic navigates to the current project's board", async () => {
  navigate.mockClear();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/team"]}>
        <AppLayout />
      </MemoryRouter>
    </QueryClientProvider>,
  );

  // bell still present beside the mic
  expect(screen.getByLabelText(/unread notifications/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /talk to the team lead/i }));
  expect(navigate).toHaveBeenCalledWith("/projects/proj-7");
});
