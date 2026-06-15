import { useQuery } from "@tanstack/react-query";
import { auditKeys, listAudit, type AuditParams } from "@/lib/api/audit";

export function useAudit(params: AuditParams) {
  return useQuery({ queryKey: auditKeys.list(params), queryFn: () => listAudit(params) });
}
