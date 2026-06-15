import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { EpicContextBand } from "./EpicContextBand";

function renderBand(props: Partial<Parameters<typeof EpicContextBand>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EpicContextBand
        projectId="p1"
        epicId="e1"
        selectedFeature={undefined}
        onSelectFeature={() => {}}
        onEditEpic={() => {}}
        {...props}
      />
    </QueryClientProvider>,
  );
}

const board = {
  epic: { id: "e1", title: "Checkout", status: "refining", body: "spec text" },
  features: [{ feature: { id: "f1", title: "Cart" }, total: 3, done: 1 }],
  tasks: [],
  total: 3,
  done: 1,
};

test("renders epic progress and feature chips", async () => {
  server.use(
    http.get("/api/projects/p1/epics/e1/board", () =>
      HttpResponse.json({ success: true, error: null, data: board })),
  );
  renderBand();
  await waitFor(() => expect(screen.getByText("Checkout")).toBeInTheDocument());
  expect(screen.getByText(/1\/3 tasks done/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Cart 1\/3/ })).toBeInTheDocument();
});

test("clicking a feature chip calls onSelectFeature", async () => {
  server.use(
    http.get("/api/projects/p1/epics/e1/board", () =>
      HttpResponse.json({ success: true, error: null, data: board })),
  );
  const onSelectFeature = vi.fn();
  renderBand({ onSelectFeature });
  await waitFor(() => screen.getByRole("button", { name: /Cart 1\/3/ }));
  await userEvent.click(screen.getByRole("button", { name: /Cart 1\/3/ }));
  expect(onSelectFeature).toHaveBeenCalledWith("f1");
});
