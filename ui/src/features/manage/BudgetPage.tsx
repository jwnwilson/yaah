import { useState } from "react";
import type { TokenUsage, UsageGroupBy } from "../../lib/api/usage";
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
        <div key={label} className="rounded border p-3">
          <div className="text-xs text-gray-500">{label}</div>
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
      <h1 className="mb-4 text-xl font-semibold">Budget</h1>
      <div className="mb-4 flex gap-2">
        <button
          onClick={() => setGroup(null)}
          className={`rounded px-3 py-1 text-sm ${group === null ? "bg-blue-600 text-white" : "border"}`}
        >
          Total
        </button>
        {GROUPS.map((g) => (
          <button
            key={g.value}
            onClick={() => setGroup(g.value)}
            className={`rounded px-3 py-1 text-sm ${group === g.value ? "bg-blue-600 text-white" : "border"}`}
          >
            {g.label}
          </button>
        ))}
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      {data && (
        <>
          <Totals t={data.totals} />
          {data.groups && (
            <table className="mt-6 w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-2">{GROUPS.find((g) => g.value === data.group_by)?.label}</th>
                  <th>Cost</th>
                  <th>Tokens</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.groups).map(([key, u]) => (
                  <tr key={key} className="border-b">
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
