from temporalio import activity

from adapters.database.uow import SqlUnitOfWork
from adapters.runtime.fake import result_of
from domain.models import RunEvent, RunEventType, RunStage, RunStatus, utc_now
from domain.runtime import AgentRuntime, RunContext
from domain.storage import StoragePort


def _heartbeat(detail: str) -> None:
    try:
        activity.heartbeat(detail)
    except RuntimeError:
        pass  # not running inside a Temporal activity (unit test)


class RunActivities:
    """Holds the session factory, runtime, and storage; exposes Temporal activities.
    The ONLY DB writer during a run."""

    def __init__(self, session_factory, runtime: AgentRuntime, storage: StoragePort) -> None:
        self._session_factory = session_factory
        self._runtime = runtime
        self._storage = storage

    def _uow(self, owner_id: str) -> SqlUnitOfWork:
        return SqlUnitOfWork(self._session_factory, required_filters={"owner_id": owner_id})

    @activity.defn(name="persist_run_state")
    def persist_run_state(self, payload: dict) -> None:
        uow = self._uow(payload["owner_id"])
        with uow.transaction():
            run = uow.runs.get(payload["run_id"])
            updates = {}
            if payload.get("status") is not None:
                updates["status"] = RunStatus(payload["status"])
            if payload.get("stage") is not None:
                updates["stage"] = RunStage(payload["stage"])
            if payload.get("cost_usd") is not None:
                updates["cost_usd"] = float(payload["cost_usd"])
            if updates:
                uow.runs.update(payload["run_id"], run.model_copy(update=updates))

    @activity.defn(name="record_event")
    def record_event(self, payload: dict) -> None:
        uow = self._uow(payload["owner_id"])
        with uow.transaction():
            uow.run_events.create(
                RunEvent(
                    run_id=payload["run_id"],
                    owner_id=payload["owner_id"],
                    stage=RunStage(payload["stage"]) if payload.get("stage") else None,
                    type=RunEventType(payload["type"]),
                    message=payload.get("message", ""),
                    created_at=utc_now(),
                )
            )

    @activity.defn(name="run_stage")
    def run_stage(self, payload: dict) -> dict:
        workspace_path = self._storage.local_path(f"runs/{payload['run_id']}")
        ctx = RunContext(
            run_id=payload["run_id"],
            stage=RunStage(payload["stage"]),
            task_title=payload["task_title"],
            acceptance_criteria=payload.get("acceptance_criteria", []),
            workspace_path=workspace_path,
            prior_artifacts=payload.get("prior_artifacts", {}),
        )
        events = []
        for event in self._runtime.run_stage(ctx):
            events.append(event)
            _heartbeat(event.message)
            self.record_event(
                {
                    "run_id": payload["run_id"],
                    "owner_id": payload["owner_id"],
                    "stage": payload["stage"],
                    "type": RunEventType.AGENT_EVENT,
                    "message": event.message,
                }
            )
        return result_of(events).model_dump()

    @activity.defn(name="cleanup_workspace")
    def cleanup_workspace(self, payload: dict) -> None:
        self._storage.delete_directory(f"runs/{payload['run_id']}/")
