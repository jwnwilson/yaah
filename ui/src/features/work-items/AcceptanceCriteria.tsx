export function AcceptanceCriteria({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="space-y-2">
      {value.map((c, i) => (
        <div key={i} className="flex gap-2">
          <input
            className="w-full rounded border p-1 text-sm"
            placeholder="criterion"
            value={c}
            onChange={(e) => onChange(value.map((v, j) => (j === i ? e.target.value : v)))}
          />
          <button
            type="button"
            className="text-sm text-red-600"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="text-sm text-blue-700" onClick={() => onChange([...value, ""])}>
        Add criterion
      </button>
    </div>
  );
}
