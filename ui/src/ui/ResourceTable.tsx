import type { ReactNode } from "react";

export interface Column<T> {
  header: string;
  render: (row: T) => ReactNode;
}

interface ResourceTableProps<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  actions?: (row: T) => ReactNode;
  empty?: string;
}

export function ResourceTable<T>({ rows, columns, rowKey, actions, empty }: ResourceTableProps<T>) {
  if (rows.length === 0) {
    return <p className="text-sm text-subtle">{empty ?? "Nothing here yet."}</p>;
  }
  return (
    <table className="w-full text-left text-sm">
      <thead className="border-b border-line text-xs uppercase tracking-wide text-subtle">
        <tr>
          {columns.map((c) => (
            <th key={c.header} className="py-2 pr-4 font-semibold">{c.header}</th>
          ))}
          {actions && <th className="py-2" />}
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {rows.map((row) => (
          <tr key={rowKey(row)} className="hover:bg-surface-hover">
            {columns.map((c) => (
              <td key={c.header} className="py-2 pr-4 align-top">{c.render(row)}</td>
            ))}
            {actions && <td className="py-2 text-right">{actions(row)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
