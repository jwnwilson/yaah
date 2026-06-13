const BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta?: PageMeta;
}

export interface PageMeta {
  total: number;
  page_size: number;
  page_number: number;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  let body: Envelope<T>;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    throw new ApiError(res.status, res.statusText || "request failed");
  }
  if (!res.ok || !body.success) {
    throw new ApiError(res.status, body.error ?? res.statusText);
  }
  return body;
}

export async function apiGet<T>(path: string): Promise<T> {
  return (await request<T>(path)).data as T;
}

export async function apiGetPage<T>(path: string): Promise<{ data: T; meta?: PageMeta }> {
  const env = await request<T>(path);
  return { data: env.data as T, meta: env.meta };
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return (await request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }))
    .data as T;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return (await request<T>(path, { method: "PATCH", body: JSON.stringify(body) })).data as T;
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return (await request<T>(path, { method: "PUT", body: JSON.stringify(body) })).data as T;
}

export async function apiDelete<T>(path: string): Promise<T> {
  return (await request<T>(path, { method: "DELETE" })).data as T;
}
