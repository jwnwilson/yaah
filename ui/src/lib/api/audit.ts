import { apiGetPage } from "./client";
import type { PageMeta } from "./client";
import type { AuditAction, AuditEvent } from "./types";

export type { AuditAction, AuditEvent } from "./types";

export interface AuditParams {
  run_id?: string;
  action?: AuditAction;
  page_number?: number;
  page_size?: number;
}

export const auditKeys = {
  list: (params: AuditParams) => ["audit", params] as const,
};

export async function listAudit(
  params: AuditParams = {},
): Promise<{ data: AuditEvent[]; meta?: PageMeta }> {
  const qs = new URLSearchParams();
  if (params.run_id) qs.set("run_id", params.run_id);
  if (params.action) qs.set("action", params.action);
  qs.set("page_number", String(params.page_number ?? 1));
  qs.set("page_size", String(params.page_size ?? 50));
  return apiGetPage<AuditEvent[]>(`/audit?${qs.toString()}`);
}
