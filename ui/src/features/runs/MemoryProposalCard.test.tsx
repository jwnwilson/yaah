import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { MemoryProposalCard } from "./MemoryProposalCard";
import type { MemoryProposal } from "@/lib/api/memory";

function proposal(overrides: Partial<MemoryProposal> = {}): MemoryProposal {
  return {
    id: "m1", run_id: "r1", project_id: "p1", branch: "agent/memory-r1",
    diff: "diff --git a/CLAUDE.md b/CLAUDE.md\n+learned", files: ["CLAUDE.md"],
    status: "proposed", pr_url: null, resolved_at: null,
    created_at: "2026-06-14T00:00:00Z", ...overrides,
  };
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryProposalCard runId="r1" />
    </QueryClientProvider>,
  );
}

test("renders the proposed proposal with files and an Apply button", async () => {
  server.use(
    http.get("/api/runs/r1/memory", () =>
      HttpResponse.json({ success: true, data: proposal(), error: null })),
  );
  renderCard();
  expect(await screen.findByText("CLAUDE.md")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /apply/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /reject/i })).toBeInTheDocument();
});

test("Apply calls the apply endpoint", async () => {
  let applied = false;
  server.use(
    http.get("/api/runs/r1/memory", () =>
      HttpResponse.json({ success: true, data: proposal(), error: null })),
    http.post("/api/runs/r1/memory/apply", () => {
      applied = true;
      return HttpResponse.json({ success: true, data: proposal({ status: "applied" }), error: null });
    }),
  );
  renderCard();
  await userEvent.click(await screen.findByRole("button", { name: /apply/i }));
  await waitFor(() => expect(applied).toBe(true));
});

test("renders nothing when there is no proposal", async () => {
  server.use(
    http.get("/api/runs/r1/memory", () =>
      HttpResponse.json({ success: true, data: null, error: null })),
  );
  const { container } = renderCard();
  await waitFor(() => expect(container).toBeEmptyDOMElement());
});
