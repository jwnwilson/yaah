import { useQuery } from "@tanstack/react-query";
import { getUsage, usageKeys, type UsageParams } from "../../lib/api/usage";

export function useUsage(params: UsageParams) {
  return useQuery({ queryKey: usageKeys.rollup(params), queryFn: () => getUsage(params) });
}
