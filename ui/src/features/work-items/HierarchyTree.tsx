import { useState } from "react";
import { useEpics, useFeatures } from "./useHierarchy";
import { useCreateWorkItem } from "./useCreateWorkItem";
import { Button } from "../../ui/Button";
import { Input, Select } from "../../ui/Field";

export function HierarchyTree({
  projectId,
  selectedFeature,
  onSelectFeature,
}: {
  projectId: string;
  selectedFeature: string | undefined;
  onSelectFeature: (featureId: string | undefined) => void;
}) {
  const epics = useEpics(projectId);
  const features = useFeatures(projectId);
  const create = useCreateWorkItem(projectId);
  const [adding, setAdding] = useState<null | "epic" | "feature">(null);
  const [title, setTitle] = useState("");
  const [parentId, setParentId] = useState<string>("");

  async function submit() {
    if (!title.trim()) return;
    if (adding === "feature" && !parentId) return;
    await create.mutateAsync({
      kind: adding!,
      title,
      parent_id: adding === "feature" ? parentId : undefined,
    });
    setTitle("");
    setAdding(null);
  }

  return (
    <div className="w-60 shrink-0 border-r border-line bg-panel p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-fg">Hierarchy</span>
      </div>
      <button className="mb-2 block text-left text-xs text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded" onClick={() => onSelectFeature(undefined)}>
        All tasks
      </button>
      <ul className="space-y-1">
        {epics.data?.map((epic) => (
          <li key={epic.id}>
            <span className="font-medium text-fg">{epic.title}</span>
            <ul className="ml-3 mt-1 space-y-1">
              {features.data
                ?.filter((f) => f.parent_id === epic.id)
                .map((f) => (
                  <li key={f.id}>
                    <button
                      className={`text-left ${selectedFeature === f.id ? "text-accent underline" : "text-muted hover:text-fg"}`}
                      onClick={() => onSelectFeature(f.id)}
                    >
                      {f.title}
                    </button>
                  </li>
                ))}
            </ul>
          </li>
        ))}
      </ul>

      <div className="mt-3 space-y-1">
        <button className="block text-xs text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded" onClick={() => setAdding("epic")}>+ Add epic</button>
        <button className="block text-xs text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded" onClick={() => setAdding("feature")}>+ Add feature</button>
      </div>

      {adding && (
        <div className="mt-2 space-y-2 rounded-md border border-line bg-surface p-2">
          {adding === "feature" && (
            <Select value={parentId} onChange={(e) => setParentId(e.target.value)}>
              <option value="">Select epic…</option>
              {epics.data?.map((e) => (
                <option key={e.id} value={e.id}>{e.title}</option>
              ))}
            </Select>
          )}
          <Input
            placeholder={adding === "epic" ? "New epic title" : "New feature title"}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={submit}>Create</Button>
            <Button size="sm" variant="ghost" onClick={() => setAdding(null)}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );
}
