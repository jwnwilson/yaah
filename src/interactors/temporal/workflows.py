import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from domain import scm
    from domain.agent.models import AgentRole
    from domain.orchestration import (
        AgentOutcome,
        AgentReport,
        MonitorVerdict,
        OrchestrationLimits,
        OrchestrationState,
        guard_exceeded,
        wave_exceeds_parallel,
    )
    from domain.projects import AutonomyLevel
    from domain.runs import RunEventType, RunStage, RunStatus
    from domain.transitions import pipeline

_STAGE_TIMEOUT = timedelta(hours=24)
_RETRY = RetryPolicy(maximum_attempts=3)


_HISTORY_LIMIT = 4000

# Worst-outcome ordering: a single failed/blocked step dominates the actor's report.
_OUTCOME_SEVERITY = {"ok": 0, "fail": 1, "blocked": 2}


@workflow.defn(name="AgentWorkflow")
class AgentWorkflow:
    """Durable child-actor: a signal-fed mailbox that drains until empty, calling the
    agent_step activity and routing outgoing messages to peer actors. The actor's return
    value carries the worst outcome + total cost it processed so the parent records a
    truthful report. continue-as-new bounds history."""

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
        worst = "ok"
        total_cost = 0.0
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
                     "team_id": inp.get("team_id"),
                     "project_id": inp.get("project_id"),
                     "memory_scope": inp.get("memory_scope", "project"),
                     "workspace_key": inp.get("workspace_key")},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                processed += 1
                total_cost += float(result.get("cost_usd", 0.0))
                outcome = result.get("outcome", "ok")
                if _OUTCOME_SEVERITY.get(outcome, 0) > _OUTCOME_SEVERITY.get(worst, 0):
                    worst = outcome
                await self._route_outgoing(inp, result.get("outgoing", []))
            self._idle = True
            if self._stop:
                break
            if (workflow.info().get_current_history_length() > _HISTORY_LIMIT
                    and not self._inbox):
                workflow.continue_as_new(inp)
        return {"role": role, "processed": processed,
                "outcome": worst, "cost_usd": total_cost}

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
    """Lead-driven parent orchestrator (the sole run path): provision -> loop(invoke_lead ->
    dispatch actors / verify / block / gate) -> PR -> LEARN -> DONE."""

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
        # Persist a terminal FAILED status if the run fails unhandled, so the run row never gets
        # stuck in `running` when an activity raises (issue #134). Re-raise so Temporal still
        # records the workflow failure. Reconcile the project either way to fill the freed slot.
        run_id, owner_id = inp["run_id"], inp["owner_id"]
        try:
            status = await self._drive(inp)
        except Exception as exc:  # noqa: BLE001 - surface terminal failure to the run row
            await self._persist(run_id, owner_id, status=RunStatus.FAILED)
            await self._event(run_id, owner_id, "implement", RunEventType.ERROR,
                              f"run failed: {exc}")
            await self._reconcile(inp)
            raise
        await self._reconcile(inp)
        return status

    async def _reconcile(self, inp: dict) -> None:
        await workflow.execute_activity(
            "reconcile_project_runs",
            {"owner_id": inp["owner_id"], "project_id": inp["project_id"]},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)

    async def _drive(self, inp: dict) -> str:
        run_id, owner_id = inp["run_id"], inp["owner_id"]
        autonomy = AutonomyLevel(inp["autonomy"])
        gates = pipeline.gates_for(autonomy)
        roles = inp.get("available_roles", [])
        role_to_agent_id = inp.get("role_to_agent_id", {})
        limits = OrchestrationLimits()
        state = OrchestrationState()
        cost = 0.0
        branch = scm.branch_name(inp["task_id"])

        await self._persist(run_id, owner_id, status=RunStatus.RUNNING, stage=RunStage.PROVISION)
        await workflow.execute_activity(
            "provision_workspace",
            {"run_id": run_id, "owner_id": owner_id, "profile": inp["profile"],
             "repo_ref": inp["repo_ref"], "branch": branch,
             "base": inp.get("base", "main")},
            start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)

        wave = 0
        verify_rounds = 0
        integration_rounds = 0
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
                 "available_roles": roles, "state": state.model_dump(mode="json"),
                 "role_to_agent_id": role_to_agent_id,
                 "work_item_id": inp.get("task_id"), "project_id": inp.get("project_id")},
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
                mv = MonitorVerdict.model_validate(verdict)
                state = state.record_verdict(mv)
                if mv.complete:
                    break
                verify_rounds += 1
                if verify_rounds >= limits.max_verify_rounds:
                    reason = ", ".join(mv.unmet) or mv.notes or "acceptance not met"
                    await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                    await self._event(run_id, owner_id, "verify", RunEventType.BLOCKED,
                                      f"acceptance not met after {verify_rounds} checks: {reason}")
                    await self._cleanup(run_id, owner_id)
                    return RunStatus.BLOCKED
                continue

            # intent == continue: dispatch a wave of instanced actors, each in its own
            # provisioned worktree/branch; run concurrently, then commit + integrate.
            dispatches = decision.get("dispatches", [])
            target_roles = [d["target_role"] for d in dispatches]
            guard = guard_exceeded(state, limits)
            if guard or not dispatches or wave_exceeds_parallel(target_roles, limits):
                reason = guard or ("max_parallel_per_role"
                                   if dispatches else "no dispatches")
                await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                await self._event(run_id, owner_id, "plan", RunEventType.BLOCKED, f"guard:{reason}")
                await self._cleanup(run_id, owner_id)
                return RunStatus.BLOCKED

            wave += 1
            await self._persist(run_id, owner_id, status=RunStatus.RUNNING,
                                stage=RunStage.IMPLEMENT)
            handles, eng_branches = [], []
            for i, d in enumerate(dispatches):
                role = d["target_role"]
                inst_branch = f"{branch}__{role}-{wave}-{i}"
                # Engineer worktrees nest under the run workspace so cleanup reclaims them,
                # but in a dotted dir that WORKSPACE_SCRATCH excludes — otherwise open_pr's
                # commit_all would record the nested worktrees as gitlinks on the task branch.
                ws_key = f"runs/{run_id}/.yaah-eng/{role}-{wave}-{i}"
                await workflow.execute_activity(
                    "provision_engineer_workspace",
                    {"run_id": run_id, "owner_id": owner_id, "profile": inp["profile"],
                     "repo_ref": inp["repo_ref"], "base": branch,
                     "branch": inst_branch, "workspace_key": ws_key},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                await self._event(run_id, owner_id, "implement",
                                  RunEventType.AGENT_DISPATCHED, f"dispatch {role} #{i}")
                child = await workflow.start_child_workflow(
                    AgentWorkflow.run,
                    {"run_id": run_id, "owner_id": owner_id, "role": role,
                     "agent_id": role_to_agent_id.get(role, role),
                     "parent_workflow_id": workflow.info().workflow_id,
                     "task_title": inp["task_title"],
                     "acceptance_criteria": inp.get("acceptance_criteria", []),
                     "team_id": inp.get("team_id"), "role_to_agent_id": role_to_agent_id,
                     "project_id": inp.get("project_id"), "work_item_id": inp.get("task_id"),
                     "memory_scope": d.get("memory_scope", "project"),
                     "workspace_key": ws_key},
                    id=f"agent-{run_id}-{role}-{wave}-{i}")
                await child.signal("deliver", {"body": d["instructions"]})
                await child.signal("stop_now")
                handles.append((role, child))
                eng_branches.append((ws_key, inst_branch))
            results = await asyncio.gather(*[h for _, h in handles])
            wave_cost = sum(float(r.get("cost_usd", 0.0)) for r in results)
            cost += wave_cost
            await self._persist(run_id, owner_id, cost_usd=cost)
            state = state.record_wave(dispatch_count=len(dispatches),
                                      messages=len(dispatches), cost=wave_cost)
            for (role, _), r in zip(handles, results):
                state = state.record_report(
                    AgentReport(role=AgentRole(role),
                                outcome=AgentOutcome(r.get("outcome", "ok")),
                                cost_usd=float(r.get("cost_usd", 0.0))))
            committed_branches = []
            for ws_key, inst_branch in eng_branches:
                ok = await workflow.execute_activity(
                    "commit_engineer_branch",
                    {"run_id": run_id, "owner_id": owner_id, "workspace_key": ws_key,
                     "title": inp["task_title"]},
                    start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
                if ok:
                    committed_branches.append(inst_branch)
            integ = await workflow.execute_activity(
                "integrate_branches",
                {"run_id": run_id, "owner_id": owner_id,
                 "workspace_key": f"runs/{run_id}", "branches": committed_branches},
                start_to_close_timeout=_STAGE_TIMEOUT, retry_policy=_RETRY)
            if integ["conflict"] is not None:
                integration_rounds += 1
                state = state.record_integration(integ["conflict"])
                if integration_rounds >= limits.max_integration_rounds:
                    await self._persist(run_id, owner_id, status=RunStatus.BLOCKED)
                    await self._event(run_id, owner_id, "implement", RunEventType.BLOCKED,
                                      f"unresolved merge conflict on {integ['conflict']['branch']}")
                    await self._cleanup(run_id, owner_id)
                    return RunStatus.BLOCKED
                await self._event(run_id, owner_id, "implement", RunEventType.QUIESCENCE_REACHED,
                                  f"wave {wave} conflict -> re-plan")
                continue
            state = state.record_integration(None)
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
            "curate_memory",
            {"run_id": run_id, "owner_id": owner_id, "task_title": inp["task_title"],
             "acceptance_criteria": inp.get("acceptance_criteria", []),
             "body": inp.get("body", "")},
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
