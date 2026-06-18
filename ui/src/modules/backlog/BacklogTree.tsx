import { useState } from "react";
import { IconButton } from "@/components/ui/IconButton";
import type { BacklogEpic, BacklogFeature, BacklogView } from "@/lib/api/backlog";
import type { WorkItem } from "@/lib/api/types";
import { EditableTitle } from "./EditableTitle";
import { InlineAdd } from "./InlineAdd";
import { type DragHandle, SortableList } from "./SortableList";
import { StatusPill } from "./StatusPill";
import type { BacklogActions } from "./useBacklog";

export interface DeleteTarget {
  id: string;
  title: string;
  kind: string;
  count: number;
}

function Grip({ handle }: { handle: DragHandle }) {
  return (
    <span
      ref={handle.setActivatorNodeRef}
      {...handle.attributes}
      {...(handle.listeners ?? {})}
      className="cursor-grab select-none px-1 text-subtle hover:text-fg"
      aria-label="drag handle"
    >
      ⠿
    </span>
  );
}

function Disclosure({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
      className="w-4 text-subtle hover:text-fg"
      aria-label={open ? "collapse" : "expand"}
    >
      {open ? "▾" : "▸"}
    </button>
  );
}

function epicDescendantCount(e: BacklogEpic): number {
  return e.features.length + e.features.reduce((n, f) => n + f.tasks.length, 0) + e.tasks.length;
}

function TaskRow({
  task,
  handle,
  actions,
  onOpen,
  onDelete,
}: {
  task: WorkItem;
  handle: DragHandle;
  actions: BacklogActions;
  onOpen: (id: string) => void;
  onDelete: (t: DeleteTarget) => void;
}) {
  return (
    <div
      className="group flex items-center gap-2 rounded px-1 py-1 hover:bg-surface-hover"
      onClick={() => onOpen(task.id)}
    >
      <Grip handle={handle} />
      <span className="text-subtle">○</span>
      <EditableTitle
        value={task.title}
        onSave={(title) => actions.rename.mutate({ id: task.id, title })}
        className="flex-1 text-sm text-fg"
      />
      <StatusPill
        status={task.status}
        onChange={(status) => actions.setStatus.mutate({ id: task.id, status })}
      />
      <IconButton
        label="delete task"
        className="opacity-0 group-hover:opacity-100"
        onClick={(e) => {
          e.stopPropagation();
          onDelete({ id: task.id, title: task.title, kind: "task", count: 0 });
        }}
      >
        ✕
      </IconButton>
    </div>
  );
}

function TaskList({
  tasks,
  parentId,
  actions,
  onOpen,
  onDelete,
}: {
  tasks: WorkItem[];
  parentId: string;
  actions: BacklogActions;
  onOpen: (id: string) => void;
  onDelete: (t: DeleteTarget) => void;
}) {
  return (
    <SortableList
      items={tasks}
      onReorder={(orderedIds) => actions.reorder.mutate({ parentId, orderedIds })}
      renderItem={(task, handle) => (
        <TaskRow
          task={task}
          handle={handle}
          actions={actions}
          onOpen={onOpen}
          onDelete={onDelete}
        />
      )}
    />
  );
}

function FeatureNode({
  bf,
  handle,
  actions,
  onOpen,
  onOpenFeature,
  onDelete,
}: {
  bf: BacklogFeature;
  handle: DragHandle;
  actions: BacklogActions;
  onOpen: (id: string) => void;
  onOpenFeature: (feature: WorkItem) => void;
  onDelete: (t: DeleteTarget) => void;
}) {
  const [open, setOpen] = useState(true);
  const { feature, tasks } = bf;
  const done = tasks.filter((t) => t.status === "done").length;
  return (
    <div className="ml-5">
      <div
        className="group flex cursor-pointer items-center gap-2 rounded px-1 py-1 hover:bg-surface-hover"
        onClick={() => onOpenFeature(feature)}
      >
        <Grip handle={handle} />
        <Disclosure open={open} onToggle={() => setOpen((v) => !v)} />
        <span className="text-subtle">✦</span>
        <span className="flex-1 truncate text-sm font-medium text-fg">{feature.title}</span>
        <span className="text-xs text-subtle">
          {done}/{tasks.length}
        </span>
        <IconButton
          label="delete feature"
          className="opacity-0 group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onDelete({ id: feature.id, title: feature.title, kind: "feature", count: tasks.length });
          }}
        >
          ✕
        </IconButton>
      </div>
      {open && (
        <div className="ml-5">
          <TaskList
            tasks={tasks}
            parentId={feature.id}
            actions={actions}
            onOpen={onOpen}
            onDelete={onDelete}
          />
          <InlineAdd
            label="task"
            className="ml-7 mt-1"
            onAdd={(title) =>
              actions.create.mutate({ kind: "task", title, parent_id: feature.id })
            }
          />
        </div>
      )}
    </div>
  );
}

function EpicNode({
  be,
  handle,
  actions,
  onOpen,
  onOpenFeature,
  onDelete,
}: {
  be: BacklogEpic;
  handle: DragHandle;
  actions: BacklogActions;
  onOpen: (id: string) => void;
  onOpenFeature: (feature: WorkItem) => void;
  onDelete: (t: DeleteTarget) => void;
}) {
  const [open, setOpen] = useState(be.active);
  const { epic } = be;
  return (
    <div className="rounded-md border border-line">
      <div
        className="group flex cursor-pointer items-center gap-2 px-2 py-2"
        onClick={() => onOpen(epic.id)}
      >
        <Grip handle={handle} />
        <Disclosure open={open} onToggle={() => setOpen((v) => !v)} />
        <span className="text-accent">◆</span>
        <span className="flex-1 truncate font-semibold text-fg">{epic.title}</span>
        <span className="text-xs text-subtle">
          {be.ready_count} ready / {be.total_tasks} · {be.done} done
          {be.in_flight_count > 0 && <> · {be.in_flight_count} running</>}
        </span>
        {be.active ? (
          <button
            type="button"
            className="rounded-full bg-accent-subtle px-2 py-0.5 text-xs font-medium text-accent"
            onClick={(e) => {
              e.stopPropagation();
              actions.deactivate.mutate(epic.id);
            }}
          >
            active
          </button>
        ) : (
          <button
            type="button"
            className="rounded-full bg-surface-hover px-2 py-0.5 text-xs font-medium text-muted hover:text-fg"
            onClick={(e) => {
              e.stopPropagation();
              actions.activate.mutate(epic.id);
            }}
          >
            activate
          </button>
        )}
        <IconButton
          label="delete epic"
          className="opacity-0 group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onDelete({
              id: epic.id,
              title: epic.title,
              kind: "epic",
              count: epicDescendantCount(be),
            });
          }}
        >
          ✕
        </IconButton>
      </div>
      {open && (
        <div className="px-2 pb-2">
          <SortableList
            items={be.features.map((bf) => ({ id: bf.feature.id, bf }))}
            onReorder={(orderedIds) => actions.reorder.mutate({ parentId: epic.id, orderedIds })}
            renderItem={(row, h) => (
              <FeatureNode
                bf={row.bf}
                handle={h}
                actions={actions}
                onOpen={onOpen}
                onOpenFeature={onOpenFeature}
                onDelete={onDelete}
              />
            )}
          />
          {be.tasks.length > 0 && (
            <div className="ml-5">
              <TaskList
                tasks={be.tasks}
                parentId={epic.id}
                actions={actions}
                onOpen={onOpen}
                onDelete={onDelete}
              />
            </div>
          )}
          <div className="ml-5 mt-1 flex gap-4">
            <InlineAdd
              label="feature"
              onAdd={(title) =>
                actions.create.mutate({ kind: "feature", title, parent_id: epic.id })
              }
            />
            <InlineAdd
              label="task"
              onAdd={(title) => actions.create.mutate({ kind: "task", title, parent_id: epic.id })}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export function BacklogTree({
  view,
  actions,
  onOpen,
  onOpenFeature,
  onDelete,
}: {
  view: BacklogView;
  actions: BacklogActions;
  onOpen: (id: string) => void;
  onOpenFeature: (feature: WorkItem) => void;
  onDelete: (t: DeleteTarget) => void;
}) {
  return (
    <div className="space-y-2">
      <SortableList
        items={view.epics.map((e) => ({ id: e.epic.id, be: e }))}
        onReorder={(orderedIds) => actions.reorder.mutate({ parentId: null, orderedIds })}
        renderItem={(row, handle) => (
          <EpicNode
            be={row.be}
            handle={handle}
            actions={actions}
            onOpen={onOpen}
            onOpenFeature={onOpenFeature}
            onDelete={onDelete}
          />
        )}
      />
    </div>
  );
}
