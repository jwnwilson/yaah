import { useState } from "react";
import type { TokenUsage, UsageGroupBy } from "@/lib/api/usage";
import { Button } from "@/ui/Button";
import { useUsage } from "./useUsage";

const GROUPS: { value: UsageGroupBy; label: string }[] = [
  { value: "stage", label: "Stage" },
  { value: "agent_role", label: "Role" },
  { value: "model", label: "Model" },
];

function fmtCost(n: number) {
  return `$${n.toFixed(2)}`;
}

function Totals({ t }: { t: TokenUsage }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        ["Cost", fmtCost(t.cost_usd)],
        ["Total tokens", t.total_tokens.toLocaleString()],
        ["Input", t.input_tokens.toLocaleString()],
        ["Output", t.output_tokens.toLocaleString()],
      ].map(([label, value]) => (
        <div key={label} className="rounded-lg border border-line bg-surface p-3">
          <div className="text-xs text-subtle">{label}</div>
          <div className="text-lg font-semibold">{value}</div>
        </div>
      ))}
    </div>
  );
}

export function BudgetPage() {
  const [group, setGroup] = useState<UsageGroupBy | null>(null);
  const { data, isLoading, isError, error } = useUsage(group ? { group_by: group } : {});

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-fg">Budget</h1>
      <div className="mb-4 flex gap-2">
        <Button size="sm" variant={group === null ? "primary" : "secondary"} onClick={() => setGroup(null)}>
          Total
        </Button>
        {GROUPS.map((g) => (
          <Button
            key={g.value}
            size="sm"
            variant={group === g.value ? "primary" : "secondary"}
            onClick={() => setGroup(g.value)}
          >
            {g.label}
          </Button>
        ))}
      </div>
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      {data && (
        <>
          <Totals t={data.totals} />
          {data.groups && (
            <table className="mt-6 w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-subtle">
                  <th className="py-2">{GROUPS.find((g) => g.value === data.group_by)?.label}</th>
                  <th>Cost</th>
                  <th>Tokens</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.groups).map(([key, u]) => (
                  <tr key={key} className="border-b border-line">
                    <td className="py-2 font-medium">{key}</td>
                    <td>{fmtCost(u.cost_usd)}</td>
                    <td>{u.total_tokens.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
