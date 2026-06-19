import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ListRow, ListSection } from "@/components/ui/ListRow";
import { PageHeader } from "@/components/ui/PageHeader";
import { CreateProjectDialog } from "./CreateProjectDialog";
import { useProjects } from "./useProjects";

export default function ProjectsPage() {
  const navigate = useNavigate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data, isLoading, isError, error } = useProjects();

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Projects" />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl p-6">
          {isLoading && <p className="text-sm text-subtle">Loading…</p>}
          {isError && <p className="text-sm text-danger">{(error as Error).message}</p>}
          {data && data.length === 0 && (
            <EmptyState
              title="No projects yet"
              description="Create your first project to spin up a board."
              action={
                <Button size="sm" onClick={() => setDialogOpen(true)}>
                  New project
                </Button>
              }
            />
          )}
          {data && data.length > 0 && (
            <ListSection>
              {data.map((p) => (
                <ListRow key={p.id} onClick={() => navigate(`/projects/${p.id}`)}>
                  <span className="flex-1 truncate font-medium text-fg">{p.name}</span>
                  <span className="truncate text-xs text-subtle">
                    {p.repo_url ?? p.local_path ?? ""}
                  </span>
                </ListRow>
              ))}
            </ListSection>
          )}
          {data && data.length > 0 && (
            <button
              type="button"
              onClick={() => setDialogOpen(true)}
              className="mt-3 text-sm text-subtle hover:text-fg"
            >
              ＋ New project
            </button>
          )}
        </div>
      </div>
      {dialogOpen && <CreateProjectDialog onClose={() => setDialogOpen(false)} />}
    </div>
  );
}
