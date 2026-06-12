import { useState } from "react";
import { useEpics, useFeatures } from "./useHierarchy";
import { useCreateWorkItem } from "./useCreateWorkItem";

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
    <div className="w-60 shrink-0 border-r p-3 text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold">Hierarchy</span>
      </div>
      <button className="mb-2 block text-left text-xs text-blue-700" onClick={() => onSelectFeature(undefined)}>
        All tasks
      </button>
      <ul className="space-y-1">
        {epics.data?.map((epic) => (
          <li key={epic.id}>
            <span className="font-medium">{epic.title}</span>
            <ul className="ml-3 mt-1 space-y-1">
              {features.data
                ?.filter((f) => f.parent_id === epic.id)
                .map((f) => (
                  <li key={f.id}>
                    <button
                      className={`text-left ${selectedFeature === f.id ? "text-blue-700 underline" : ""}`}
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
        <button className="block text-xs text-blue-700" onClick={() => setAdding("epic")}>+ Add epic</button>
        <button className="block text-xs text-blue-700" onClick={() => setAdding("feature")}>+ Add feature</button>
      </div>

      {adding && (
        <div className="mt-2 space-y-2 rounded border p-2">
          {adding === "feature" && (
            <select className="w-full rounded border p-1" value={parentId} onChange={(e) => setParentId(e.target.value)}>
              <option value="">Select epic…</option>
              {epics.data?.map((e) => (
                <option key={e.id} value={e.id}>{e.title}</option>
              ))}
            </select>
          )}
          <input
            className="w-full rounded border p-1"
            placeholder={adding === "epic" ? "New epic title" : "New feature title"}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div className="flex gap-2">
            <button className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white" onClick={submit}>Create</button>
            <button className="text-xs" onClick={() => setAdding(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
