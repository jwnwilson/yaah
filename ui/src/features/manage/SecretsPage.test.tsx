import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { SecretsPage } from "./SecretsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><SecretsPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

const seed = (has_value: boolean) => [
  { id: "s1", owner_id: "u", name: "GITHUB_TOKEN", description: "", has_value, created_at: "2026-01-01T00:00:00Z" },
];

test("lists secrets with status badge and creates one", async () => {
  const rows = seed(false);
  server.use(
    http.get("/api/secrets", () => HttpResponse.json({ success: true, data: rows, error: null, meta: { total: rows.length, page_size: 200, page_number: 1 } })),
    http.post("/api/secrets", async ({ request }) => {
      const b = (await request.json()) as { name: string };
      const created = { id: "s2", owner_id: "u", name: b.name, description: "", has_value: false, created_at: "2026-01-02T00:00:00Z" };
      rows.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
  );
  renderPage();
  expect(await screen.findByText("GITHUB_TOKEN")).toBeInTheDocument();
  expect(screen.getByText(/empty/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /new secret/i }));
  await userEvent.type(screen.getByLabelText(/name/i), "OPENAI_KEY");
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));
  await waitFor(() => expect(screen.getByText("OPENAI_KEY")).toBeInTheDocument());
});

test("set value submits the value and never renders it back", async () => {
  const rows = seed(false);
  server.use(
    http.get("/api/secrets", () => HttpResponse.json({ success: true, data: rows, error: null, meta: { total: rows.length, page_size: 200, page_number: 1 } })),
    http.put("/api/secrets/s1/value", async () => {
      rows[0] = { ...rows[0], has_value: true };
      return HttpResponse.json({ success: true, data: rows[0], error: null });
    }),
  );
  renderPage();
  await screen.findByText("GITHUB_TOKEN");
  await userEvent.click(screen.getByRole("button", { name: /set value/i }));
  const input = screen.getByLabelText(/value/i);
  await userEvent.type(input, "ghp_supersecret");
  await userEvent.click(screen.getByRole("button", { name: /save/i }));
  await waitFor(() => expect(screen.getByText(/configured/i)).toBeInTheDocument());  // badge flipped empty -> configured
  expect(screen.queryByText(/ghp_supersecret/)).not.toBeInTheDocument();
  expect(document.body.innerHTML).not.toContain("ghp_supersecret");
});
