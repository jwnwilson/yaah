import { useQuery } from "@tanstack/react-query";
import { getRun, getRunUsage, listRunAudit, listRunEvents, runKeys } from "@/lib/api/runs";
import type { Run, RunStatus } from "@/lib/api/types";

const TERMINAL: ReadonlySet<RunStatus> = new Set(["done", "failed", "blocked", "cancelled"]);
const POLL_MS = 3000;

export function isTerminal(status: RunStatus | undefined): boolean {
  return status != null && TERMINAL.has(status);
}

/** Poll while the run is non-terminal; stop once it reaches a terminal status. */
function pollInterval(run: Run | undefined): number | false {
  return isTerminal(run?.status) ? false : POLL_MS;
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: runKeys.detail(runId),
    queryFn: () => getRun(runId),
    refetchInterval: (query) => pollInterval(query.state.data),
  });
}

export function useRunEvents(runId: string, run: Run | undefined) {
  return useQuery({
    queryKey: runKeys.events(runId),
    queryFn: () => listRunEvents(runId),
    refetchInterval: () => pollInterval(run),
  });
}

export function useRunUsage(runId: string, run: Run | undefined) {
  return useQuery({
    queryKey: runKeys.usage(runId),
    queryFn: () => getRunUsage(runId),
    refetchInterval: () => pollInterval(run),
  });
}

export function useRunAudit(runId: string, run: Run | undefined) {
  return useQuery({
    queryKey: runKeys.audit(runId),
    queryFn: () => listRunAudit(runId),
    refetchInterval: () => pollInterval(run),
  });
}
