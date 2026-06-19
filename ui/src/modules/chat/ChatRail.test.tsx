import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, vi } from "vitest";
import { server } from "@/test/server";
import { ChatRail } from "./ChatRail";

let dictationSupported = true;
const startSpy = vi.fn();
vi.mock("@/modules/chat/useSpeechDictation", () => ({
  useSpeechDictation: ({ onTranscript }: { onTranscript: (t: string) => void }) => ({
    supported: dictationSupported,
    listening: false,
    start: () => {
      startSpy();
      onTranscript("voice text");
    },
    stop: vi.fn(),
    toggle: () => onTranscript("voice text"),
  }),
}));

beforeEach(() => {
  dictationSupported = true;
  startSpy.mockClear();
});

function renderRail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChatRail projectId="p1" />
    </QueryClientProvider>,
  );
}

test("sends a message and shows the assistant reply", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
    http.post("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, error: null, data: {
        session_id: "s1", reply: "Drafted an epic", created_items: [] } })),
  );
  renderRail();
  await userEvent.type(screen.getByPlaceholderText(/message the team lead/i), "build login");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  await waitFor(() => expect(screen.getByText("Drafted an epic")).toBeInTheDocument());
});

test("epic-scoped: shows a proposed epic edit and accepts it", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
    http.post("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, error: null, data: {
        session_id: "s1", reply: "Refined the epic", created_items: [],
        proposed_epic_update: { body: "new spec", acceptance_criteria: ["works"] } } })),
    http.patch("/api/work-items/e1", () =>
      HttpResponse.json({ success: true, error: null, data: { id: "e1" } })),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ChatRail projectId="p1" epicId="e1" />
    </QueryClientProvider>,
  );
  await userEvent.type(screen.getByPlaceholderText(/message the team lead/i), "cart flow");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  await waitFor(() => expect(screen.getByText(/suggested epic spec/i)).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: /apply/i }));
  await waitFor(() => expect(screen.queryByText(/suggested epic spec/i)).not.toBeInTheDocument());
});

test("shows a proposed edit to an existing item and applies it", async () => {
  let patched = false;
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
    http.post("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, error: null, data: {
        session_id: "s1", reply: "Proposed an edit", created_items: [],
        proposed_updates: [
          { id: "f1", kind: "feature", current_title: "Login flow", title: null,
            body: "Tighten the spec", acceptance_criteria: ["validates input"] },
        ] } })),
    http.patch("/api/work-items/f1", () => {
      patched = true;
      return HttpResponse.json({ success: true, error: null, data: { id: "f1" } });
    }),
  );
  renderRail();
  await userEvent.type(screen.getByPlaceholderText(/message the team lead/i), "refine login");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  await waitFor(() => expect(screen.getByText(/edit feature: login flow/i)).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: /apply/i }));
  await waitFor(() => expect(patched).toBe(true));
  await waitFor(() => expect(screen.queryByText(/edit feature: login flow/i)).not.toBeInTheDocument());
});

test("dictation fills the message input", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
  );
  renderRail();
  await userEvent.click(screen.getByLabelText(/dictate|voice/i));
  expect(screen.getByPlaceholderText(/message the team lead/i)).toHaveValue("voice text");
});

test("autoDictate starts dictation once and notifies the launcher", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
  );
  const onConsumed = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ChatRail projectId="p1" autoDictate onDictateConsumed={onConsumed} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(startSpy).toHaveBeenCalledTimes(1));
  expect(onConsumed).toHaveBeenCalledTimes(1);
});

test("does not auto-start dictation when autoDictate is false", async () => {
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
  );
  const onConsumed = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ChatRail projectId="p1" autoDictate={false} onDictateConsumed={onConsumed} />
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.getByPlaceholderText(/message the team lead/i)).toBeInTheDocument(),
  );
  expect(startSpy).not.toHaveBeenCalled();
  expect(onConsumed).not.toHaveBeenCalled();
});

test("mic button is absent when speech recognition is unsupported", async () => {
  dictationSupported = false;
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
  );
  renderRail();
  await waitFor(() =>
    expect(screen.getByPlaceholderText(/message the team lead/i)).toBeInTheDocument(),
  );
  expect(screen.queryByLabelText(/dictate|voice/i)).not.toBeInTheDocument();
});

test("reports its dictation listening state to the launcher", async () => {
  const onListeningChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ChatRail projectId="p1" onListeningChange={onListeningChange} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(onListeningChange).toHaveBeenCalledWith(false));
});

test("shows a working indicator while the team lead processes a message", async () => {
  let resolve: (v: unknown) => void = () => {};
  server.use(
    http.get("/api/projects/p1/chat", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: { total: 0, page_size: 50, page_number: 1 } })),
    http.post("/api/projects/p1/chat", async () => {
      await new Promise((r) => (resolve = r));
      return HttpResponse.json({ success: true, error: null, data: { session_id: "s1", reply: "done", created_items: [] } });
    }),
  );
  renderRail();
  await userEvent.type(screen.getByPlaceholderText(/message the team lead/i), "build login");
  await userEvent.click(screen.getByRole("button", { name: /send/i }));
  await waitFor(() => expect(screen.getByText(/team lead is working/i)).toBeInTheDocument());
  resolve(null);
  await waitFor(() => expect(screen.getByText("done")).toBeInTheDocument());
});
