import { useState } from "react";
import { Link } from "react-router-dom";
import { useProjects } from "./useProjects";
import { CreateProjectDialog } from "./CreateProjectDialog";

export default function ProjectsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data, isLoading, isError, error } = useProjects();

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Projects</h1>
        <button onClick={() => setDialogOpen(true)} className="rounded bg-blue-600 px-3 py-1 text-sm text-white">
          New project
        </button>
      </div>
      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">{(error as Error).message}</p>}
      <ul className="space-y-2">
        {data?.map((p) => (
          <li key={p.id} className="rounded border p-3">
            <Link to={`/projects/${p.id}`} className="font-medium text-blue-700">{p.name}</Link>
          </li>
        ))}
      </ul>
      {dialogOpen && <CreateProjectDialog onClose={() => setDialogOpen(false)} />}
    </div>
  );
}
