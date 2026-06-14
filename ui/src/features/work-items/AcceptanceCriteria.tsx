import { Input } from "../../ui/Field";

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
          <Input
            className="text-sm"
            placeholder="criterion"
            value={c}
            onChange={(e) => onChange(value.map((v, j) => (j === i ? e.target.value : v)))}
          />
          <button
            type="button"
            className="text-sm text-danger hover:text-danger/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="text-sm text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded" onClick={() => onChange([...value, ""])}>
        Add criterion
      </button>
    </div>
  );
}
