import { useState } from "react";
import { useCreateProject } from "./useCreateProject";

export function CreateProjectDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [localPath, setLocalPath] = useState("");
  const create = useCreateProject();

  const canSubmit = name.trim() !== "" && (repoUrl.trim() !== "" || localPath.trim() !== "");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    await create.mutateAsync({
      name,
      repo_url: repoUrl.trim() || undefined,
      local_path: localPath.trim() || undefined,
    });
    onClose();
  }

  return (
    <div className="fixed inset-0 grid place-items-center bg-black/30">
      <form onSubmit={submit} className="w-96 space-y-3 rounded bg-white p-4 shadow">
        <h2 className="text-lg font-semibold">New project</h2>
        <label className="block text-sm">
          Name
          <input className="mt-1 w-full rounded border p-2" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block text-sm">
          Repo URL
          <input className="mt-1 w-full rounded border p-2" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} />
        </label>
        <label className="block text-sm">
          Local path
          <input className="mt-1 w-full rounded border p-2" value={localPath} onChange={(e) => setLocalPath(e.target.value)} />
        </label>
        {!canSubmit && <p className="text-xs text-gray-500">Name and a repo URL or local path are required.</p>}
        {create.isError && <p className="text-xs text-red-600">{(create.error as Error).message}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded px-3 py-1 text-sm">Cancel</button>
          <button type="submit" disabled={!canSubmit || create.isPending} className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50">Create</button>
        </div>
      </form>
    </div>
  );
}
