import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
import { HierarchyTree } from "./HierarchyTree";

function renderTree(onSelectFeature = () => {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <HierarchyTree projectId="p1" selectedFeature={undefined} onSelectFeature={onSelectFeature} />
    </QueryClientProvider>,
  );
}

test("lists epics and features and creates an epic", async () => {
  const items: any[] = [
    { id: "e1", project_id: "p1", owner_id: "u", kind: "epic", parent_id: null, title: "Epic One", body: "", acceptance_criteria: [], status: "draft", created_at: "x", updated_at: "x" },
  ];
  server.use(
    http.get("/api/projects/p1/work-items", ({ request }) => {
      const url = new URL(request.url);
      const kind = url.searchParams.get("kind");
      const data = kind ? items.filter((i) => i.kind === kind) : items;
      return HttpResponse.json({ success: true, data, error: null, meta: { total: data.length, page_size: 200, page_number: 1 } });
    }),
    http.post("/api/projects/p1/work-items", async ({ request }) => {
      const body = (await request.json()) as { title: string; kind: string };
      const created = { id: "e2", project_id: "p1", owner_id: "u", kind: body.kind, parent_id: null, title: body.title, body: "", acceptance_criteria: [], status: "draft", created_at: "x", updated_at: "x" };
      items.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
  );

  renderTree();
  expect(await screen.findByText("Epic One")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /add epic/i }));
  await userEvent.type(screen.getByPlaceholderText(/new epic title/i), "Epic Two");
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));
  await waitFor(() => expect(screen.getByText("Epic Two")).toBeInTheDocument());
});
