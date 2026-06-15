import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/ui/Button";
import { Card } from "@/ui/Card";
import { EmptyState } from "@/ui/EmptyState";
import { CreateProjectDialog } from "./CreateProjectDialog";
import { useProjects } from "./useProjects";

export default function ProjectsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data, isLoading, isError, error } = useProjects();

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">Projects</h1>
        <Button size="sm" onClick={() => setDialogOpen(true)}>New project</Button>
      </div>
      {isLoading && <p className="text-sm text-subtle">Loading…</p>}
      {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <EmptyState
          title="No projects yet"
          description="Create your first project to spin up a board."
          action={<Button size="sm" onClick={() => setDialogOpen(true)}>New project</Button>}
        />
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((p) => (
          <Card key={p.id} className="p-4 transition-colors hover:bg-surface-hover">
            <Link to={`/projects/${p.id}`} className="font-medium text-fg hover:text-accent">
              {p.name}
            </Link>
          </Card>
        ))}
      </div>
      {dialogOpen && <CreateProjectDialog onClose={() => setDialogOpen(false)} />}
    </div>
  );
}
