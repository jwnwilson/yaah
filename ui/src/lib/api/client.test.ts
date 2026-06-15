import { afterEach, describe, expect, it, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "@/test/server";
import { apiGet, apiPost, ApiError } from "./client";

afterEach(() => server.resetHandlers());

test("apiGet unwraps the data envelope", async () => {
  server.use(
    http.get("/api/ping", () =>
      HttpResponse.json({ success: true, data: { pong: 1 }, error: null }),
    ),
  );
  const data = await apiGet<{ pong: number }>("/ping");
  expect(data.pong).toBe(1);
});

test("apiGet throws ApiError with status and message on failure", async () => {
  server.use(
    http.get("/api/boom", () =>
      HttpResponse.json({ success: false, data: null, error: "nope" }, { status: 409 }),
    ),
  );
  await expect(apiGet("/boom")).rejects.toMatchObject({ status: 409, message: "nope" });
  await expect(apiGet("/boom")).rejects.toBeInstanceOf(ApiError);
});

test("apiPost returns unwrapped data and reads meta when asked", async () => {
  server.use(
    http.post("/api/things", () =>
      HttpResponse.json({ success: true, data: { id: "x" }, error: null }, { status: 201 }),
    ),
  );
  const data = await apiPost<{ id: string }>("/things", { name: "a" });
  expect(data.id).toBe("x");
});

describe("api client base URL", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("defaults to the /api dev proxy when no env override is set", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "");
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ success: true, data: { status: "ok" }, error: null }), {
          status: 200,
        }),
      );
    const { apiGet } = await import("./client");
    await apiGet("/health");
    expect(fetchSpy).toHaveBeenCalledWith("/api/health", expect.anything());
  });

  it("uses VITE_API_BASE_URL as an absolute base when set", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.yaah.jwnwilson.co.uk");
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ success: true, data: { status: "ok" }, error: null }), {
          status: 200,
        }),
      );
    const { apiGet } = await import("./client");
    await apiGet("/health");
    expect(fetchSpy).toHaveBeenCalledWith(
      "https://api.yaah.jwnwilson.co.uk/health",
      expect.anything(),
    );
  });
});
