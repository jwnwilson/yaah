import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from domain import scm
    from domain.models import (
        AgentRole,
        AutonomyLevel,
        RunEventType,
        RunStage,
        RunStatus,
    )
    from domain.orchestration import (
        AgentOutcome,
        AgentReport,
        MonitorVerdict,
        OrchestrationLimits,
        OrchestrationState,
        guard_exceeded,
    )
    from domain.transitions import pipeline

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

        _branch = scm.branch_name(inp["task_id"])
        _pr_title = scm.pr_title(inp["task_title"])
        _pr_body = scm.pr_body(inp["task_title"], inp.get("body", ""),
                               inp.get("acceptance_criteria", []))

        i = 0
        while i < len(pipeline.STAGES):
            if self._cancelled:
                await self._persist(run_id, owner_id, status=RunStatus.CANCELLED)
                await self._cleanup(run_id, owner_id)
                return RunStatus.CANCELLED

            stage = pipeline.STAGES[i]
            await self._persist(run_id, owner_id, status=RunStatus.RUNNING, stage=stage)
            await self._event(run_id, owner_id, stage, RunEventType.STAGE_STARTED)

            if stage == RunStage.PROVISION:
                await workflow.execute_activity(
                    "provision_workspace",
                    {"run_id": run_id, "owner_id": owner_id, "profile": inp["profile"],
                     "repo_ref": inp["repo_ref"], "branch": _branch},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                result = {"outcome": "ok"}
            elif stage == RunStage.PR:
                result = await workflow.execute_activity(
                    "open_pr",
                    {"run_id": run_id, "owner_id": owner_id, "profile": inp["profile"],
                     "branch": _branch, "base": inp.get("base", "main"),
                     "title": _pr_title, "body": _pr_body},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
            else:
                result = await workflow.execute_activity(
                    "run_stage",
                    {
                        "run_id": run_id,
                        "owner_id": owner_id,
                        "stage": stage,
                        "task_title": inp["task_title"],
                        "acceptance_criteria": inp.get("acceptance_criteria", []),
                        "team_id": inp.get("team_id"),
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

        # Curator memory edits were made during LEARN; capture them before teardown.
        await workflow.execute_activity(
            "capture_memory",
            {"run_id": run_id, "owner_id": owner_id,
             "project_id": inp["project_id"], "base": inp.get("base", "main"),
             "profile": inp["profile"], "autonomy": inp["autonomy"],
             "repo_ref": inp["repo_ref"]},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
        await self._persist(run_id, owner_id, status=RunStatus.DONE, stage=RunStage.LEARN)
        await self._cleanup(run_id, owner_id)
        return RunStatus.DONE


_HISTORY_LIMIT = 4000


@workflow.defn(name="AgentWorkflow")
class AgentWorkflow:
    """Durable child-actor: a signal-fed mailbox that drains until empty, calling the
    agent_step activity, routing outgoing messages to peer actors, and reporting brief
    completion to the parent. continue-as-new bounds history."""

    def __init__(self) -> None:
        self._inbox: list[dict] = []
        self._idle = False
        self._stop = False

    @workflow.signal
    def deliver(self, msg: dict) -> None:
        self._inbox.append(msg)
        self._idle = False

    @workflow.signal
    def stop_now(self) -> None:
        self._stop = True

    @workflow.query
    def queue_depth(self) -> int:
        return len(self._inbox)

    @workflow.query
    def is_idle(self) -> bool:
        return self._idle

    @workflow.run
    async def run(self, inp: dict) -> dict:
        run_id, owner_id, role = inp["run_id"], inp["owner_id"], inp["role"]
        processed = 0
        while True:
            await workflow.wait_condition(lambda: bool(self._inbox) or self._stop)
            while self._inbox:  # drain everything currently queued before honoring stop
                msg = self._inbox.pop(0)
                self._idle = False
                result = await workflow.execute_activity(
                    "agent_step",
                    {"run_id": run_id, "owner_id": owner_id, "role": role,
                     "incoming": msg.get("body", ""), "task_title": inp["task_title"],
                     "acceptance_criteria": inp.get("acceptance_criteria", []),
                     "team_id": inp.get("team_id")},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                processed += 1
                await self._route_outgoing(inp, result.get("outgoing", []))
                if result.get("completed_brief"):
                    await self._signal_safe(
                        inp["parent_workflow_id"], "agent_report",
                        {"role": role, "outcome": result.get("outcome", "ok")})
            self._idle = True
            if self._stop:
                break
            if (workflow.info().get_current_history_length() > _HISTORY_LIMIT
                    and not self._inbox):
                workflow.continue_as_new(inp)
        return {"role": role, "processed": processed}

    async def _route_outgoing(self, inp: dict, outgoing: list[dict]) -> None:
        if not outgoing:
            return
        messages: list[dict] = []
        for out in outgoing:
            is_agent = out.get("recipient_kind") == "agent"
            recipient_role = out.get("recipient_role")
            recipient_agent_id = inp["role_to_agent_id"].get(recipient_role) if is_agent else None
            if is_agent and recipient_agent_id is None:
                continue  # unknown role: nothing to deliver or persist
            messages.append({
                "owner_id": inp["owner_id"], "sender_kind": "agent",
                "sender_agent_id": inp["agent_id"], "recipient_kind": out["recipient_kind"],
                "recipient_agent_id": recipient_agent_id, "kind": out.get("kind", "chat"),
                "subject": out.get("subject", ""), "body": out["body"],
                "run_id": inp["run_id"], "work_item_id": inp.get("work_item_id"),
                "project_id": inp.get("project_id"),
            })
            if is_agent:
                peer_id = f"agent-{inp['run_id']}-{recipient_role}"
                if peer_id != workflow.info().workflow_id:
                    await self._signal_safe(peer_id, "deliver", {"body": out["body"]})
        if messages:
            await workflow.execute_activity(
                "persist_messages", {"owner_id": inp["owner_id"], "messages": messages},
                start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)

    async def _signal_safe(self, workflow_id: str, signal_name: str, arg: dict) -> None:
        try:
            await workflow.get_external_workflow_handle(workflow_id).signal(signal_name, arg)
        except Exception:  # noqa: BLE001 - target may not be running; don't crash the actor
            pass


@workflow.defn(name="OrchestratorWorkflow")
class OrchestratorWorkflow:
    """Lead-driven parent orchestrator: provision -> loop(invoke_lead -> dispatch actors
    / verify / block / gate) -> PR -> LEARN -> DONE. Additive: RunWorkflow is unchanged."""

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

    async def _persist(self, run_id, owner_id, **fields) -> None:
        await workflow.execute_activity(
            "persist_run_state", {"run_id": run_id, "owner_id": owner_id, **fields},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)

    async def _event(self, run_id, owner_id, stage, type_, message="") -> None:
        await workflow.execute_activity(
            "record_event",
            {"run_id": run_id, "owner_id": owner_id, "stage": stage,
             "type": type_, "message": message},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)

    async def _cleanup(self, run_id, owner_id) -> None:
        await workflow.execute_activity(
            "cleanup_workspace", {"run_id": run_id, "owner_id": owner_id},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)

    async def _await_gate(self) -> str:
        await workflow.wait_condition(
            lambda: self._approved or self._rejected or self._cancelled)
        if self._cancelled:
            return "cancelled"
        if self._rejected:
            return "rejected"
        self._approved = False
        return "approved"

    @workflow.run
    async def run(self, inp: dict) -> str:
        run_id, owner_id = inp["run_id"], inp["owner_id"]
        autonomy = AutonomyLevel(inp["autonomy"])
        gates = pipeline.gates_for(autonomy)
        roles = inp.get("available_roles", [])
        limits = OrchestrationLimits()
        state = OrchestrationState()
        cost = 0.0
        branch = scm.branch_name(inp["task_id"])

        await self._persist(run_id, owner_id, status=RunStatus.RUNNING, stage=RunStage.PROVISION)
        await workflow.execute_activity(
            "provision_workspace",
            {"run_id": run_id, "owner_id": owner_id, "profile": inp["profile"],
             "repo_ref": inp["repo_ref"], "branch": branch},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)

        wave = 0
        while True:
            if self._cancelled:
                await self._persist(run_id, owner_id, status=RunStatus.CANCELLED)
                await self._cleanup(run_id, owner_id)
                return RunStatus.CANCELLED

            res = await workflow.execute_activity(
                "invoke_lead",
                {"run_id": run_id, "owner_id": owner_id, "task_title": inp["task_title"],
                 "acceptance_criteria": inp.get("acceptance_criteria", []),
                 "body": inp.get("body", ""), "team_id": inp.get("team_id"),
                 "available_roles": roles, "state": state.model_dump(mode="json")},
                start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
            cost += res.get("cost_usd", 0.0)
            await self._persist(run_id, owner_id, cost_usd=cost)
            decision = res["decision"]
            intent = decision["intent"]

            if intent == "block":
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(run_id, owner_id, "plan", RunEventType.BLOCKED,
                                  decision.get("rationale", ""))
                await self._cleanup(run_id, owner_id)
                return RunStatus.BLOCKED

            if intent == "needs_human":
                await self._persist(run_id, owner_id, status=RunStatus.AWAITING_APPROVAL)
                await self._event(run_id, owner_id, "plan", RunEventType.GATE_OPENED)
                outcome = await self._await_gate()
                if outcome == "cancelled":
                    await self._persist(run_id, owner_id, status=RunStatus.CANCELLED)
                    await self._cleanup(run_id, owner_id)
                    return RunStatus.CANCELLED
                if outcome == "rejected":
                    await self._persist(run_id, owner_id, status=RunStatus.FAILED)
                    await self._event(run_id, owner_id, "plan", RunEventType.GATE_RESOLVED,
                                      "rejected")
                    await self._cleanup(run_id, owner_id)
                    return RunStatus.FAILED
                await self._event(run_id, owner_id, "plan", RunEventType.GATE_RESOLVED, "approved")
                continue

            if intent == "verify":
                verdict = await workflow.execute_activity(
                    "run_monitor",
                    {"run_id": run_id, "owner_id": owner_id, "task_title": inp["task_title"],
                     "acceptance_criteria": inp.get("acceptance_criteria", []),
                     "team_id": inp.get("team_id")},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                state = state.record_verdict(MonitorVerdict.model_validate(verdict))
                if verdict.get("complete"):
                    break
                continue

            # intent == continue: dispatch a wave of actors
            dispatches = decision.get("dispatches", [])
            guard = guard_exceeded(state, limits)
            if guard or not dispatches:
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(run_id, owner_id, "plan", RunEventType.BLOCKED,
                                  f"guard:{guard}" if guard else "no dispatches")
                await self._cleanup(run_id, owner_id)
                return RunStatus.BLOCKED

            wave += 1
            await self._persist(run_id, owner_id, status=RunStatus.RUNNING,
                                stage=RunStage.IMPLEMENT)
            handles = []
            for d in dispatches:
                role = d["target_role"]
                await self._event(run_id, owner_id, "implement", RunEventType.AGENT_DISPATCHED,
                                  f"dispatch {role}")
                child = await workflow.start_child_workflow(
                    AgentWorkflow.run,
                    {"run_id": run_id, "owner_id": owner_id, "role": role, "agent_id": role,
                     "parent_workflow_id": workflow.info().workflow_id,
                     "task_title": inp["task_title"],
                     "acceptance_criteria": inp.get("acceptance_criteria", []),
                     "team_id": inp.get("team_id"), "role_to_agent_id": {},
                     "project_id": inp.get("project_id"), "work_item_id": inp.get("task_id")},
                    id=f"agent-{run_id}-{role}-{wave}")
                await child.signal("deliver", {"body": d["instructions"]})
                await child.signal("stop_now")
                handles.append((role, child))
            await asyncio.gather(*[h for _, h in handles])
            state = state.record_wave(dispatch_count=len(dispatches),
                                      messages=len(dispatches), cost=0.0)
            for role, _ in handles:
                state = state.record_report(
                    AgentReport(role=AgentRole(role), outcome=AgentOutcome.OK))
            await self._event(run_id, owner_id, "implement", RunEventType.QUIESCENCE_REACHED,
                              f"wave {wave} complete")

        # verified complete -> optional PR gate, then PR + LEARN
        if RunStage.PR in gates:
            await self._persist(run_id, owner_id, status=RunStatus.AWAITING_APPROVAL,
                                stage=RunStage.PR)
            await self._event(run_id, owner_id, "pr", RunEventType.GATE_OPENED)
            outcome = await self._await_gate()
            if outcome == "cancelled":
                await self._persist(run_id, owner_id, status=RunStatus.CANCELLED)
                await self._cleanup(run_id, owner_id)
                return RunStatus.CANCELLED
            if outcome == "rejected":
                await self._persist(run_id, owner_id, status=RunStatus.FAILED)
                await self._event(run_id, owner_id, "pr", RunEventType.GATE_RESOLVED, "rejected")
                await self._cleanup(run_id, owner_id)
                return RunStatus.FAILED
            await self._event(run_id, owner_id, "pr", RunEventType.GATE_RESOLVED, "approved")

        await workflow.execute_activity(
            "open_pr",
            {"run_id": run_id, "owner_id": owner_id, "profile": inp["profile"], "branch": branch,
             "base": inp.get("base", "main"), "title": scm.pr_title(inp["task_title"]),
             "body": scm.pr_body(inp["task_title"], inp.get("body", ""),
                                 inp.get("acceptance_criteria", []))},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
        await workflow.execute_activity(
            "capture_memory",
            {"run_id": run_id, "owner_id": owner_id, "project_id": inp["project_id"],
             "base": inp.get("base", "main"), "profile": inp["profile"],
             "autonomy": inp["autonomy"], "repo_ref": inp["repo_ref"]},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
        await self._persist(run_id, owner_id, status=RunStatus.DONE, stage=RunStage.LEARN)
        await self._cleanup(run_id, owner_id)
        return RunStatus.DONE
