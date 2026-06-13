from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from domain import pipeline
    from domain.models import AutonomyLevel, RunEventType, RunStage, RunStatus

_STAGE_TIMEOUT = timedelta(hours=24)
_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn(name="RunWorkflow")
class RunWorkflow:
    def __init__(self) -> None:
        self._approved = False
        self._rejected = False
        self._cancelled = False

    @workflow.signal
    def approve(self) -> None:
        self._approved = True

    @workflow.signal
    def reject(self) -> None:
        self._rejected = True

    @workflow.signal
    def cancel(self) -> None:
        self._cancelled = True

    async def _persist(self, run_id: str, owner_id: str, **fields) -> None:
        await workflow.execute_activity(
            "persist_run_state",
            {"run_id": run_id, "owner_id": owner_id, **fields},
            start_to_close_timeout=_STAGE_TIMEOUT,
            retry_policy=_RETRY,
        )

    async def _event(
        self, run_id: str, owner_id: str, stage: str, type_: str, message: str = ""
    ) -> None:
        await workflow.execute_activity(
            "record_event",
            {
                "run_id": run_id,
                "owner_id": owner_id,
                "stage": stage,
                "type": type_,
                "message": message,
            },
            start_to_close_timeout=_STAGE_TIMEOUT,
            retry_policy=_RETRY,
        )

    async def _cleanup(self, run_id: str, owner_id: str) -> None:
        await workflow.execute_activity(
            "cleanup_workspace",
            {"run_id": run_id, "owner_id": owner_id},
            start_to_close_timeout=_STAGE_TIMEOUT,
            retry_policy=_RETRY,
        )

    @workflow.run
    async def run(self, inp: dict) -> str:
        run_id = inp["run_id"]
        owner_id = inp["owner_id"]
        autonomy = AutonomyLevel(inp["autonomy"])
        gates = pipeline.gates_for(autonomy)
        cost = 0.0
        verify_loops = 0

        i = 0
        while i < len(pipeline.STAGES):
            if self._cancelled:
                await self._persist(run_id, owner_id, status=RunStatus.CANCELLED)
                await self._cleanup(run_id, owner_id)
                return RunStatus.CANCELLED

            stage = pipeline.STAGES[i]
            await self._persist(run_id, owner_id, status=RunStatus.RUNNING, stage=stage)
            await self._event(run_id, owner_id, stage, RunEventType.STAGE_STARTED)

            result = await workflow.execute_activity(
                "run_stage",
                {
                    "run_id": run_id,
                    "owner_id": owner_id,
                    "stage": stage,
                    "task_title": inp["task_title"],
                    "acceptance_criteria": inp.get("acceptance_criteria", []),
                },
                start_to_close_timeout=_STAGE_TIMEOUT,
                retry_policy=_RETRY,
            )
            cost += float(result.get("cost_usd", 0.0))
            await self._persist(run_id, owner_id, cost_usd=cost)
            await self._event(run_id, owner_id, stage, RunEventType.STAGE_COMPLETED)

            if result["outcome"] == "blocked":
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(run_id, owner_id, stage, RunEventType.BLOCKED)
                await self._cleanup(run_id, owner_id)
                return RunStatus.BLOCKED

            if stage == RunStage.VERIFY and result["outcome"] == "fail":
                verify_loops += 1
                if pipeline.should_retry_verify(verify_loops):
                    i = pipeline.STAGES.index(RunStage.IMPLEMENT)
                    continue
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(
                    run_id, owner_id, stage, RunEventType.BLOCKED, "verify exhausted"
                )
                await self._cleanup(run_id, owner_id)
                return RunStatus.BLOCKED

            if stage in gates:
                await self._persist(run_id, owner_id, status=RunStatus.AWAITING_APPROVAL)
                await self._event(run_id, owner_id, stage, RunEventType.GATE_OPENED)
                await workflow.wait_condition(
                    lambda: self._approved or self._rejected or self._cancelled
                )
                if self._cancelled:
                    await self._persist(run_id, owner_id, status=RunStatus.CANCELLED)
                    await self._cleanup(run_id, owner_id)
                    return RunStatus.CANCELLED
                if self._rejected:
                    await self._persist(run_id, owner_id, status=RunStatus.FAILED)
                    await self._event(
                        run_id, owner_id, stage, RunEventType.GATE_RESOLVED, "rejected"
                    )
                    await self._cleanup(run_id, owner_id)
                    return RunStatus.FAILED
                self._approved = False  # reset for the next gate
                await self._event(
                    run_id, owner_id, stage, RunEventType.GATE_RESOLVED, "approved"
                )

            i += 1

        await self._persist(run_id, owner_id, status=RunStatus.DONE, stage=RunStage.LEARN)
        await self._cleanup(run_id, owner_id)
        return RunStatus.DONE
