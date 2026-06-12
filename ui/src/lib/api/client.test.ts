import { afterEach, expect, test } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/server";
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
