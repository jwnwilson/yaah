import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Field, Input } from "@/components/ui/Field";
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
    <Dialog title="New project" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Repo URL"><Input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} /></Field>
        <Field label="Local path"><Input value={localPath} onChange={(e) => setLocalPath(e.target.value)} /></Field>
        {!canSubmit && <p className="text-xs text-subtle">Name and a repo URL or local path are required.</p>}
        {create.isError && <p className="text-xs text-danger">{(create.error as Error).message}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" disabled={!canSubmit} loading={create.isPending}>Create</Button>
        </div>
      </form>
    </Dialog>
  );
}
