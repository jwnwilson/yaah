import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { server } from "@/test/server";
import { McpServersPage } from "./McpServersPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter><McpServersPage /></MemoryRouter></QueryClientProvider>);
}

test("lists and creates an MCP server with a tool-allowlist chip", async () => {
  const rows: unknown[] = [];
  let posted: { tool_allowlist: string[] } | null = null;
  server.use(
    http.get("/api/mcp-servers", () => HttpResponse.json({ success: true, data: rows, error: null, meta: { total: rows.length, page_size: 200, page_number: 1 } })),
    http.post("/api/mcp-servers", async ({ request }) => {
      posted = (await request.json()) as { tool_allowlist: string[] };
      const created = { id: "m1", owner_id: "u", name: "github", transport: "stdio", command_or_url: "npx server", tool_allowlist: posted.tool_allowlist, created_at: "2026-01-02T00:00:00Z" };
      rows.push(created);
      return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
    }),
  );
  renderPage();
  await waitFor(() => expect(screen.getByText(/no mcp servers/i)).toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: /new mcp server/i }));
  await userEvent.type(screen.getByLabelText(/name/i), "github");
  await userEvent.type(screen.getByLabelText(/command or url/i), "npx server");
  const toolInput = screen.getByLabelText(/add tool/i);
  await userEvent.type(toolInput, "mcp__github__search{enter}");
  expect(screen.getByText("mcp__github__search")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));

  await waitFor(() => expect(posted).toEqual(expect.objectContaining({ tool_allowlist: ["mcp__github__search"] })));
  await waitFor(() => expect(screen.getByText("github")).toBeInTheDocument());
});
