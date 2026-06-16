import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

test("uploading a chosen file posts it and refreshes the list", async () => {
  let uploadedFilename = "";
  let getCount = 0;
  server.use(
    http.get("/api/work-items/wi1/attachments", () => {
      getCount += 1;
      return HttpResponse.json({ success: true, error: null, data: [] });
    }),
    http.post("/api/work-items/wi1/attachments", () => {
      uploadedFilename = "posted";
      return HttpResponse.json({
        success: true,
        error: null,
        data: { id: "a9", work_item_id: "wi1", filename: "n.png", content_type: "image/png", size_bytes: 3, origin: "human", created_at: "" },
      });
    }),
  );
  renderAttachments();
  await waitFor(() => expect(getCount).toBe(1));
  const file = new File(["abc"], "n.png", { type: "image/png" });
  await userEvent.upload(screen.getByLabelText(/upload attachment/i), file);
  // choosing a file fires the upload POST...
  await waitFor(() => expect(uploadedFilename).toBe("posted"));
  // ...and success invalidates the list query -> a refetch happens
  await waitFor(() => expect(getCount).toBeGreaterThanOrEqual(2));
});

test("delete calls the API and refreshes the list", async () => {
  let deletedId = "";
  let getCount = 0;
  server.use(
    http.get("/api/work-items/wi1/attachments", () => {
      getCount += 1;
      return HttpResponse.json({ success: true, error: null, data: [list[0]] });
    }),
    http.delete("/api/attachments/a1", () => {
      deletedId = "a1";
      return HttpResponse.json({ success: true, error: null, data: { deleted: "a1" } });
    }),
  );
  renderAttachments();
  await waitFor(() => screen.getByRole("button", { name: /delete/i }));
  await userEvent.click(screen.getByRole("button", { name: /delete/i }));
  await waitFor(() => expect(deletedId).toBe("a1"));
  await waitFor(() => expect(getCount).toBeGreaterThanOrEqual(2));
});
