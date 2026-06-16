import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { Attachments } from "./Attachments";

function renderAttachments() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Attachments itemId="wi1" />
    </QueryClientProvider>,
  );
}

const list = [
  { id: "a1", work_item_id: "wi1", filename: "shot.png", content_type: "image/png", size_bytes: 12, origin: "human", created_at: "" },
  { id: "a2", work_item_id: "wi1", filename: "notes.md", content_type: "text/markdown", size_bytes: 40, origin: "human", created_at: "" },
];

test("renders an image thumbnail and a download link", async () => {
  server.use(
    http.get("/api/work-items/wi1/attachments", () =>
      HttpResponse.json({ success: true, error: null, data: list })),
  );
  renderAttachments();
  await waitFor(() => expect(screen.getByRole("img", { name: /shot.png/i })).toBeInTheDocument());
  expect(screen.getByRole("img", { name: /shot.png/i })).toHaveAttribute("src", "/api/attachments/a1");
  expect(screen.getByRole("link", { name: /notes.md/i })).toHaveAttribute("href", "/api/attachments/a2");
});
