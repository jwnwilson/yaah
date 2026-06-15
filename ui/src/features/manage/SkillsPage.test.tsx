import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { SkillsPage } from "./SkillsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><SkillsPage /></MemoryRouter></QueryClientProvider>);
}

test("lists, creates, and deletes a skill", async () => {
  const rows = [{ id: "k1", owner_id: "u", name: "code-search", description: "grep/AST", source: "builtin", created_at: "2026-01-01T00:00:00Z" }];
  server.use(
    http.get("/api/skills", () => HttpResponse.json({ success: true, data: rows, error: null, meta: { total: rows.length, page_size: 200, page_number: 1 } })),
    http.post("/api/skills", async ({ request }) => {
      const b = (await request.json()) as { name: string };
      const created = { id: "k2", owner_id: "u", name: b.name, description: "", source: "", created_at: "2026-01-02T00:00:00Z" };
      rows.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
    http.delete("/api/skills/k1", () => { rows.splice(0, 1); return HttpResponse.json({ success: true, data: { deleted: "k1" }, error: null }); }),
  );
  renderPage();
  expect(await screen.findByText("code-search")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /new skill/i }));
  await userEvent.type(screen.getByLabelText(/name/i), "rag-query");
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));
  await waitFor(() => expect(screen.getByText("rag-query")).toBeInTheDocument());

  await userEvent.click(screen.getAllByRole("button", { name: /delete/i })[0]); // row delete -> opens dialog
  const deleteButtons = screen.getAllByRole("button", { name: /^delete$/i });
  await userEvent.click(deleteButtons[deleteButtons.length - 1]); // dialog confirm (last)
  await waitFor(() => expect(screen.queryByText("code-search")).not.toBeInTheDocument());
});
