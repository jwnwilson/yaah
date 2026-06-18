import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { BacklogEpic } from "@/lib/api/backlog";

export function EpicRow({
  projectId,
  item,
  onActivate,
  onDeactivate,
  busy,
}: {
  projectId: string;
  item: BacklogEpic;
  onActivate: () => void;
  onDeactivate: () => void;
  busy: boolean;
}) {
  const { epic, active, ready_count, total_tasks, done, in_flight_count } = item;
  return (
    <Card className="flex items-center gap-4 p-4">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Link
            to={`/projects/${projectId}?epic=${epic.id}`}
            className="truncate font-medium text-fg hover:text-accent"
          >
            {epic.title}
          </Link>
          {active && <Badge tone="accent">active</Badge>}
        </div>
        <p className="mt-1 text-xs text-subtle">
          {ready_count} ready / {total_tasks} tasks · {done} done
          {in_flight_count > 0 && <> · {in_flight_count} running</>}
        </p>
      </div>
      {active ? (
        <Button size="sm" variant="secondary" onClick={onDeactivate} disabled={busy}>
          Deactivate
        </Button>
      ) : (
        <Button size="sm" onClick={onActivate} disabled={busy}>
          Activate
        </Button>
      )}
    </Card>
  );
}
