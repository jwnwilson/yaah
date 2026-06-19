import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSpeechDictation } from "./useSpeechDictation";

class FakeRecognition {
  lang = "";
  continuous = false;
  interimResults = false;
  onresult: ((e: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  start = vi.fn(() => {
    started = true;
  });
  stop = vi.fn(() => {
    this.onend?.();
  });
  abort = vi.fn();
}
let started = false;

afterEach(() => {
  started = false;
  delete (window as unknown as Record<string, unknown>).SpeechRecognition;
});

describe("useSpeechDictation", () => {
  it("reports unsupported when the API is absent", () => {
    const { result } = renderHook(() => useSpeechDictation({ onTranscript: vi.fn() }));
    expect(result.current.supported).toBe(false);
  });

  it("starts/stops and emits final transcripts", () => {
    let rec: FakeRecognition;
    (window as unknown as Record<string, unknown>).SpeechRecognition = function () {
      rec = new FakeRecognition();
      return rec;
    } as unknown;
    const onTranscript = vi.fn();
    const { result } = renderHook(() => useSpeechDictation({ onTranscript }));
    expect(result.current.supported).toBe(true);

    act(() => result.current.start());
    expect(result.current.listening).toBe(true);
    expect(started).toBe(true);

    act(() =>
      rec!.onresult?.({
        resultIndex: 0,
        results: { length: 1, 0: { 0: { transcript: "hello lead" }, isFinal: true } },
      }),
    );
    expect(onTranscript).toHaveBeenCalledWith("hello lead");

    act(() => result.current.stop());
    expect(result.current.listening).toBe(false);
  });
});
