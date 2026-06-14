import "@testing-library/jest-dom/vitest";
import { transferableAbortController } from "node:util";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// jsdom installs its own AbortController/AbortSignal whose instances are not
// recognised by the global Request (backed by undici, which MSW uses to
// intercept). That mismatch makes any client-side React Router navigation
// reject with "Expected signal to be an instance of AbortSignal". Restore the
// native AbortController/AbortSignal that the Request realm accepts.
const NativeAbortController = transferableAbortController()
  .constructor as typeof AbortController;
const NativeAbortSignal = transferableAbortController().signal
  .constructor as typeof AbortSignal;
globalThis.AbortController = NativeAbortController;
globalThis.AbortSignal = NativeAbortSignal;

// jsdom does not install a working Storage here — `localStorage` resolves to a
// bare object without setItem/getItem/clear. Install a minimal in-memory
// Storage so code that persists to localStorage (e.g. theme) is testable.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length() {
    return this.store.size;
  }
  clear() {
    this.store.clear();
  }
  getItem(key: string) {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null;
  }
}
const memoryStorage = new MemoryStorage();
for (const target of [globalThis, globalThis.window]) {
  if (target) {
    Object.defineProperty(target, "localStorage", {
      value: memoryStorage,
      configurable: true,
      writable: true,
    });
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
