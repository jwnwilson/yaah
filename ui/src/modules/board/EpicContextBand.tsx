import { useEpicBoard } from "./useEpicBoard";

interface EpicContextBandProps {
  projectId: string;
  epicId: string;
  selectedFeature: string | undefined;
  onSelectFeature: (featureId: string | undefined) => void;
  onEditItem: (itemId: string) => void;
}

export function EpicContextBand({
  projectId,
  epicId,
  selectedFeature,
  onSelectFeature,
  onEditItem,
}: EpicContextBandProps) {
  const { data } = useEpicBoard(projectId, epicId);
  if (!data) return null;
  const { epic, features, total, done } = data;

  const chip = (active: boolean) =>
    `rounded px-2 py-0.5 text-xs ${active ? "bg-accent text-accent-fg" : "bg-panel text-muted hover:text-fg"}`;

  return (
    <div className="border-b border-line bg-surface px-4 py-2">
      <div className="flex items-center gap-2">
        <button
          className="font-semibold text-fg hover:underline"
          onClick={() => onEditItem(epic.id)}
        >
          {epic.title}
        </button>
        <span className="text-xs text-muted">[{epic.status}]</span>
        <span className="text-xs text-muted">
          {done}/{total} tasks done
        </span>
      </div>
      {epic.body && (
        <p className="mt-1 line-clamp-1 text-xs text-muted">{epic.body}</p>
      )}
      <div className="mt-2 flex flex-wrap gap-1">
        <button
          className={chip(!selectedFeature)}
          onClick={() => onSelectFeature(undefined)}
        >
          All tasks
        </button>
        {features.length === 0 && (
          <span className="text-xs text-muted">
            No features yet — ask the lead to break this epic down.
          </span>
        )}
        {features.map((fp) => (
          <span key={fp.feature.id} className="inline-flex items-center">
            <button
              className={chip(selectedFeature === fp.feature.id)}
              onClick={() => onSelectFeature(fp.feature.id)}
            >
              {fp.feature.title} {fp.done}/{fp.total}
            </button>
            <button
              className="ml-0.5 text-xs text-muted hover:text-fg"
              aria-label={`edit ${fp.feature.title}`}
              onClick={() => onEditItem(fp.feature.id)}
            >
              ✎
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}
