# Voice dictation for the team-lead chat — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user **speak to the team lead** instead of typing — a 🎤 mic button in the `ChatRail` input that transcribes speech (via the browser Web Speech API) into the chat input, which the user reviews and sends.

**Architecture:** Pure-frontend, no backend/STT service. A reusable `useSpeechDictation` hook wraps `window.SpeechRecognition`/`webkitSpeechRecognition` (audio never leaves the browser; no cost). `ChatRail` adds a mic toggle that appends transcribed text to its existing `text` state. Feature-detected: the mic is hidden when the browser doesn't support speech recognition. No auto-send — the transcript fills the input for review, matching the existing type-and-Send flow.

**Tech Stack:** React + TypeScript, Web Speech API, vitest. Single UI PR; no backend.

**Conventions:** UI in `ui/`; run tests with `pnpm vitest run <path>` (never `pnpm test -- <path>`); gate = `pnpm vitest run` + `pnpm lint` (eslint + tsc) + `pnpm build`. The Web Speech API isn't in jsdom, so tests stub `window.SpeechRecognition`.

---

## Task 1: `useSpeechDictation` hook (Web Speech API)

**Files:**
- Create: `ui/src/modules/chat/useSpeechDictation.ts`
- Create: `ui/src/modules/chat/speech.d.ts` (minimal Web Speech API types for tsc)
- Test: `ui/src/modules/chat/useSpeechDictation.test.ts`

- [ ] **Step 1: minimal types** — `ui/src/modules/chat/speech.d.ts` (the API isn't in TS's lib.dom by default):

```ts
interface SpeechRecognitionResultLike {
  0: { transcript: string };
  isFinal: boolean;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [i: number]: SpeechRecognitionResultLike };
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}
interface Window {
  SpeechRecognition?: { new (): SpeechRecognitionLike };
  webkitSpeechRecognition?: { new (): SpeechRecognitionLike };
}
```

- [ ] **Step 2: write the failing test** — `useSpeechDictation.test.ts`. Stub a fake recognition on `window`, drive results via `renderHook` + `act`:

```ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSpeechDictation } from "./useSpeechDictation";

class FakeRecognition {
  lang = ""; continuous = false; interimResults = false;
  onresult: ((e: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  start = vi.fn(() => { started = true; });
  stop = vi.fn(() => { this.onend?.(); });
  abort = vi.fn();
}
let started = false;

afterEach(() => { started = false; delete (window as unknown as Record<string, unknown>).SpeechRecognition; });

describe("useSpeechDictation", () => {
  it("reports unsupported when the API is absent", () => {
    const { result } = renderHook(() => useSpeechDictation({ onTranscript: vi.fn() }));
    expect(result.current.supported).toBe(false);
  });

  it("starts/stops and emits final transcripts", () => {
    let rec: FakeRecognition;
    (window as unknown as Record<string, unknown>).SpeechRecognition =
      function () { rec = new FakeRecognition(); return rec; } as unknown;
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useSpeechDictation({ onTranscript }));
    expect(result.current.supported).toBe(true);

    act(() => result.current.start());
    expect(result.current.listening).toBe(true);
    expect(started).toBe(true);

    act(() => rec!.onresult?.({ resultIndex: 0, results: { length: 1, 0: { 0: { transcript: "hello lead" }, isFinal: true } } }));
    expect(onTranscript).toHaveBeenCalledWith("hello lead");

    act(() => result.current.stop());
    expect(result.current.listening).toBe(false);
  });
});
```

- [ ] **Step 3: run it, confirm FAIL** — `cd ui && pnpm vitest run src/modules/chat/useSpeechDictation.test.ts` (module not found).

- [ ] **Step 4: implement** — `ui/src/modules/chat/useSpeechDictation.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";

interface Options {
  onTranscript: (text: string) => void;   // called with each FINAL transcript chunk
  lang?: string;
}

export function useSpeechDictation({ onTranscript, lang = "en-US" }: Options) {
  const Ctor = typeof window !== "undefined"
    ? window.SpeechRecognition ?? window.webkitSpeechRecognition
    : undefined;
  const supported = Boolean(Ctor);
  const [listening, setListening] = useState(false);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const cbRef = useRef(onTranscript);
  cbRef.current = onTranscript;

  const stop = useCallback(() => {
    recRef.current?.stop();
  }, []);

  const start = useCallback(() => {
    if (!Ctor || recRef.current) return;
    const rec = new Ctor();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = false;     // v1: commit only final chunks to the input
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) cbRef.current(r[0].transcript.trim());
      }
    };
    const cleanup = () => { recRef.current = null; setListening(false); };
    rec.onend = cleanup;
    rec.onerror = cleanup;
    recRef.current = rec;
    rec.start();
    setListening(true);
  }, [Ctor, lang]);

  const toggle = useCallback(() => (listening ? stop() : start()), [listening, start, stop]);

  useEffect(() => () => recRef.current?.abort(), []);   // stop on unmount

  return { supported, listening, start, stop, toggle };
}
```

- [ ] **Step 5: run + lint** — `pnpm vitest run src/modules/chat/useSpeechDictation.test.ts` (pass); `pnpm lint`.

- [ ] **Step 6: commit** — `git add ui/src/modules/chat/useSpeechDictation.ts ui/src/modules/chat/speech.d.ts ui/src/modules/chat/useSpeechDictation.test.ts && git commit -m "feat: useSpeechDictation hook (Web Speech API)"`

---

## Task 2: mic button in the ChatRail input

**Files:**
- Modify: `ui/src/modules/chat/ChatRail.tsx`
- Test: `ui/src/modules/chat/ChatRail.test.tsx`

Current form (for reference):
```tsx
<form className="flex gap-1 border-t border-line p-2" onSubmit={handleSubmit}>
  <Input placeholder="Message the team lead…" value={text} onChange={(e) => setText(e.target.value)} />
  <Button type="submit" size="sm" loading={send.isPending}>Send</Button>
</form>
```

- [ ] **Step 1: write the failing test** — append to `ChatRail.test.tsx` (mock the hook so the test is deterministic; the real Web Speech API isn't in jsdom). Mirror the file's existing render setup (it already renders `ChatRail` with a project; reuse that harness).

```tsx
// at top of the file:
vi.mock("@/modules/chat/useSpeechDictation", () => ({
  useSpeechDictation: ({ onTranscript }: { onTranscript: (t: string) => void }) => ({
    supported: true, listening: false,
    start: () => onTranscript("voice text"), stop: vi.fn(), toggle: () => onTranscript("voice text"),
  }),
}));

it("dictation fills the message input", async () => {
  // ...render ChatRail (existing harness)...
  await userEvent.click(screen.getByLabelText(/dictate|voice/i));
  expect(screen.getByPlaceholderText(/message the team lead/i)).toHaveValue("voice text");
});
```
Also add a test that when `useSpeechDictation` returns `supported: false`, the mic button is absent (use a second `vi.mock` variant or override per-test).

- [ ] **Step 2: run, confirm FAIL** — `pnpm vitest run src/modules/chat/ChatRail.test.tsx`.

- [ ] **Step 3: implement** — in `ChatRail.tsx`:
  - import `IconButton` from `@/components/ui/IconButton` and `useSpeechDictation`.
  - wire the hook: `const dictation = useSpeechDictation({ onTranscript: (t) => setText((prev) => (prev ? prev + " " : "") + t) });`
  - in the form, before the Send button, render the mic only when supported:
```tsx
{dictation.supported && (
  <IconButton
    label={dictation.listening ? "Stop dictation" : "Dictate to the team lead"}
    title="Voice input"
    aria-pressed={dictation.listening}
    onClick={dictation.toggle}
    className={dictation.listening ? "text-danger animate-pulse" : undefined}
  >
    <span aria-hidden="true">🎤</span>
  </IconButton>
)}
```
  (`setText` is already in scope. Appending keeps any typed text + spoken text.)

- [ ] **Step 4: run + lint + build** — `pnpm vitest run src/modules/chat` (pass), `pnpm lint`, `pnpm build`.

- [ ] **Step 5: commit** — `git add ui/src/modules/chat/ChatRail.tsx ui/src/modules/chat/ChatRail.test.tsx && git commit -m "feat: mic dictation button in the team-lead chat input"`

---

## Final validation
- [ ] `pnpm vitest run` all green; `pnpm lint` (eslint + tsc) clean; `pnpm build` succeeds.
- [ ] Manual (Chrome/Edge/Safari): open a project → **Team lead** → click 🎤, allow the mic, speak → words appear in the input → edit if needed → **Send**. In an unsupported browser the mic is absent (typing still works).
- [ ] Open PR: `feat: voice dictation to talk to the team lead`.

## Decisions & deferred
- **Web Speech API (not server STT):** zero backend/cost, audio stays in the browser; the trade-off is browser support (Chromium + Safari good; Firefox limited) — handled by feature-detection + hiding the mic. Server-side STT (Whisper/Deepgram) is a future option if cross-browser/accuracy demands it.
- **Fill-not-autosend:** the transcript lands in the input for review; the user sends. (Auto-send on a pause is a possible later toggle.)
- **Interim results off in v1:** only final chunks append, avoiding flicker/duplication in the input; live interim preview is a later refinement.
- **The existing global top-right 🎤 (added in #154):** out of scope here. Options for a follow-up: (a) remove it (dictation now lives where you talk to the lead), or (b) wire it as a global shortcut that opens the current project's team-lead chat and starts dictation — which needs lifting the page-local `showChat` state into shared state. Recommend deciding when this PR lands.
