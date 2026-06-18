import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ChatRail } from "@/modules/chat/ChatRail";
import { BacklogTree, type DeleteTarget } from "./BacklogTree";
import { DetailPeek } from "./DetailPeek";
import { InlineAdd } from "./InlineAdd";
import { useBacklog } from "./useBacklog";

export default function BacklogPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const actions = useBacklog(projectId);
  const { query, create, remove, setCap } = actions;
  const data = query.data;
  const [openId, setOpenId] = useState<string | null>(null);
  const [target, setTarget] = useState<DeleteTarget | null>(null);
  const [showChat, setShowChat] = useState(false);

  if (query.isLoading) return <p className="p-6 text-sm text-subtle">Loading…</p>;
  if (query.isError)
    return <p className="p-6 text-sm text-danger">{(query.error as Error).message}</p>;
  if (!data) return null;

  return (
    <div className="flex h-full">
      <div className="mx-auto w-full max-w-4xl flex-1 overflow-y-auto p-6">
        <div className="mb-4 flex items-center justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight text-fg">Backlog</h1>
          <div className="flex items-center gap-4">
            <span className="text-xs text-subtle">
              running {data.in_flight} / {data.max_concurrent_runs} · queued {data.queued}
            </span>
            <Button size="sm" variant="secondary" onClick={() => setShowChat((v) => !v)}>
              {showChat ? "Hide chat" : "Team lead"}
            </Button>
            <label className="flex items-center gap-2 text-sm text-muted">
              Max runs
              <input
                type="number"
                min={1}
                defaultValue={data.max_concurrent_runs}
                onBlur={(e) => {
                  const v = Number(e.target.value);
                  if (v >= 1 && v !== data.max_concurrent_runs) setCap.mutate(v);
                }}
                className="w-14 rounded-md border border-line bg-surface px-2 py-1 text-fg"
              />
            </label>
          </div>
        </div>

        {data.epics.length === 0 ? (
          <EmptyState
            title="No epics yet"
            description="Add your first epic to start planning."
          />
        ) : (
          <BacklogTree
            view={data}
            actions={actions}
            onOpen={setOpenId}
            onOpenFeature={(feature) =>
              navigate(
                `/projects/${projectId}?epic=${feature.parent_id ?? ""}` +
                  `&feature=${feature.id}&item=${feature.id}`,
              )
            }
            onDelete={setTarget}
          />
        )}

        <div className="mt-3">
          <InlineAdd
            label="epic"
            className="text-sm"
            onAdd={(title) => create.mutate({ kind: "epic", title })}
          />
        </div>
      </div>

      {showChat && <ChatRail projectId={projectId} />}

      {openId && (
        <DetailPeek projectId={projectId} itemId={openId} onClose={() => setOpenId(null)} />
      )}

      {target && (
        <ConfirmDialog
          title={`Delete ${target.kind}?`}
          message={
            target.count > 0
              ? `"${target.title}" and ${target.count} item${target.count === 1 ? "" : "s"} beneath it will be permanently deleted.`
              : `"${target.title}" will be permanently deleted.`
          }
          pending={remove.isPending}
          error={remove.isError ? (remove.error as Error).message : undefined}
          onConfirm={() =>
            remove.mutate(target.id, {
              onSuccess: () => {
                if (openId === target.id) setOpenId(null);
                setTarget(null);
              },
            })
          }
          onClose={() => setTarget(null)}
        />
      )}
    </div>
  );
}
