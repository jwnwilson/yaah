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

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
