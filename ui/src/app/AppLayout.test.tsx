import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { routes } from "./router";

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
