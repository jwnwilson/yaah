from temporalio import activity

from adapters.agent.notify.ports import NotificationDispatcher
from adapters.database.uow import SqlUnitOfWork
from adapters.storage.ports import StoragePort
from domain.agent import AgentRuntime, RunContext, result_of
from domain.agent.models import AgentRole
from domain.base import utc_now
from domain.errors import IntegrityConflict
from domain.notifications import (
    Notification,
    NotificationCategory,
    NotificationSeverity,
    NotificationSource,
    notification_for_event,
    resolves,
)
from domain.runs import RunEvent, RunEventType, RunStage, RunStatus
from domain.scm import WORKSPACE_SCRATCH
from domain.usage import TokenUsage, UsageRecord
from interactors.scheduling import reconcile_project

_MAX_LEAD_RETRIES = 2  # bounded re-prompts when the lead emits an invalid decision


def _heartbeat(detail: str) -> None:
    try:
        activity.heartbeat(detail)
    except RuntimeError:
        pass  # not running inside a Temporal activity (unit test)


class RunActivities:
    """Holds the session factory, runtime, storage, git, and forge; exposes Temporal activities.
    The ONLY DB writer during a run."""

    def __init__(self, session_factory, runtime: AgentRuntime, storage: StoragePort,
                 git, forge, *, cipher=None,
                 notifier: NotificationDispatcher | None = None,
                 settings=None, run_client=None) -> None:
        self._session_factory = session_factory
        self._runtime = runtime
        self._storage = storage
        self._git = git
        self._forge = forge
        self._cipher = cipher
        self._notifier = notifier or NotificationDispatcher([])
        self._settings = settings
        self._run_client = run_client

    def _uow(self, owner_id: str) -> SqlUnitOfWork:
        return SqlUnitOfWork(self._session_factory, required_filters={"owner_id": owner_id})

    def _ingest_tool_audit(self, owner_id: str, run_id: str) -> None:
        import json

        from domain.audit import AuditAction, AuditEvent
        from domain.base import utc_now
        from domain.runs import RunStage
        try:
            raw = self._storage.read_text(f"runs/{run_id}/audit.jsonl")
            if not raw:
                return
            uow = self._uow(owner_id)
            with uow.transaction():
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    action = (AuditAction.TOOL_ALLOWED if rec.get("decision") == "allow"
                              else AuditAction.TOOL_DENIED)
                    stage_val = rec.get("stage")
                    uow.audit_events.create(AuditEvent(
                        run_id=run_id, owner_id=owner_id,
                        stage=RunStage(stage_val) if stage_val else None,
                        actor="", action=action,
                        detail={"tool": rec.get("tool", ""), "reason": rec.get("reason", "")},
                        created_at=utc_now(),
                    ))
            self._storage.delete(f"runs/{run_id}/audit.jsonl")  # consume -> idempotent
        except Exception:  # noqa: BLE001 - audit ingest is best-effort, never fails the stage
            pass

    def _record_audit(
        self, owner_id: str, run_id: str, stage: str, actor: str, detail: dict
    ) -> None:
        from domain.audit import AuditAction, AuditEvent
        from domain.base import utc_now
        from domain.runs import RunStage
        try:
            uow = self._uow(owner_id)
            with uow.transaction():
                uow.audit_events.create(AuditEvent(
                    run_id=run_id, owner_id=owner_id,
                    stage=RunStage(stage) if stage else None,
                    actor=actor, action=AuditAction.CAPABILITY_GRANTED,
                    detail=detail, created_at=utc_now(),
                ))
        except Exception:  # noqa: BLE001 - audit is best-effort, never fails the stage
            pass

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
            if payload.get("branch") is not None:
                updates["branch"] = payload["branch"]
            if payload.get("pr_url") is not None:
                updates["pr_url"] = payload["pr_url"]
            if updates:
                uow.runs.update(payload["run_id"], run.model_copy(update=updates))

    @activity.defn(name="record_event")
    def record_event(self, payload: dict) -> None:
        owner_id = payload["owner_id"]
        run_id = payload["run_id"]
        ev_type = RunEventType(payload["type"])
        stage = RunStage(payload["stage"]) if payload.get("stage") else None
        to_deliver: list[Notification] = []
        uow = self._uow(owner_id)
        with uow.transaction():
            ev = RunEvent(run_id=run_id, owner_id=owner_id, stage=stage, type=ev_type,
                          message=payload.get("message", ""), created_at=utc_now())
            uow.run_events.create(ev)
            if ev_type == RunEventType.GATE_RESOLVED:
                open_notifs = uow.notifications.list(
                    filters={"run_id": run_id, "resolved_at__isnull": True}, page_size=200
                ).results
                for n in open_notifs:
                    if resolves(n, ev):
                        uow.notifications.update(
                            n.id, n.model_copy(update={"resolved_at": utc_now()}))
            else:
                run = uow.runs.get(run_id)
                notif = notification_for_event(ev, run=run)
                if notif is not None and not self._has_open_gate_notification(uow, run_id, notif):
                    to_deliver.append(uow.notifications.create(notif))
        for n in to_deliver:
            self._notifier.deliver(n)

    def _has_open_gate_notification(self, uow, run_id: str, candidate: Notification) -> bool:
        if candidate.action is None:
            return False
        existing = uow.notifications.list(
            filters={"run_id": run_id, "resolved_at__isnull": True}, page_size=200
        ).results
        return any(n.action is not None for n in existing)

    @activity.defn(name="record_notification")
    def record_notification(self, payload: dict) -> None:
        owner_id = payload["owner_id"]
        run_id = payload["run_id"]
        category = NotificationCategory(payload.get("category", "update"))
        severity = NotificationSeverity(payload.get("severity", "info"))
        to_deliver: list[Notification] = []
        uow = self._uow(owner_id)
        with uow.transaction():
            run = uow.runs.get(run_id)
            notif = Notification(
                owner_id=owner_id, source=NotificationSource.AGENT, category=category,
                severity=severity, title=payload["title"], body=payload.get("body", ""),
                run_id=run_id, work_item_id=run.task_id,
            )
            to_deliver.append(uow.notifications.create(notif))
        for n in to_deliver:
            self._notifier.deliver(n)

    @activity.defn(name="record_usage")
    def record_usage(self, payload: dict) -> None:
        """Write one UsageRecord per model for a stage execution and recompute the run's
        token counters from all its rows. Idempotent: duplicate (run, stage, role, model)
        inserts are swallowed; counters are recomputed, never incremented."""
        owner_id = payload["owner_id"]
        run_id = payload["run_id"]
        stage = RunStage(payload["stage"])
        role = AgentRole(payload["agent_role"]) if payload.get("agent_role") else None
        uow = self._uow(owner_id)
        with uow.transaction():
            run = uow.runs.get(run_id)
            task = uow.work_items.get(run.task_id)
            for model_id, u in (payload.get("model_usage") or {}).items():
                usage = TokenUsage(**u)
                record = UsageRecord(
                    owner_id=owner_id, run_id=run_id, work_item_id=run.task_id,
                    project_id=task.project_id, stage=stage, agent_role=role,
                    model_id=model_id,
                    input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    cache_creation_tokens=usage.cache_creation_tokens,
                    cost_usd=usage.cost_usd,
                )
                try:
                    # Savepoint: a duplicate (retry) conflict rolls back only this
                    # insert, leaving the session usable for the recompute below.
                    with uow.session.begin_nested():
                        uow.usage.create(record)
                except IntegrityConflict:
                    pass  # already recorded on a prior attempt
            rows = uow.usage.list(filters={"run_id": run_id}, page_size=1000).results
            totals = TokenUsage()
            for r in rows:
                totals = totals.combine(TokenUsage(
                    input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                    cache_read_tokens=r.cache_read_tokens,
                    cache_creation_tokens=r.cache_creation_tokens))
            uow.runs.update(run_id, run.model_copy(update={
                "input_tokens": totals.input_tokens,
                "output_tokens": totals.output_tokens,
                "cache_read_tokens": totals.cache_read_tokens,
                "cache_creation_tokens": totals.cache_creation_tokens,
            }))

    @activity.defn(name="persist_messages")
    def persist_messages(self, payload: dict) -> None:
        from domain.messages import Message
        owner_id = payload["owner_id"]
        uow = self._uow(owner_id)
        with uow.transaction():
            for raw in payload.get("messages", []):
                msg = Message(**raw)
                try:
                    uow.messages.get(msg.id)
                    continue  # already persisted
                except Exception:  # noqa: BLE001 - not found -> create
                    uow.messages.create(msg)

    def _manifest_for_role(self, owner_id: str, team_id, role):
        """Assemble the AgentManifest for `role` on `team_id` (skills/mcps/secrets),
        mirroring run_stage's assembly. Returns (manifest, role) or (None, None)."""
        if not team_id or role is None:
            return None, None
        from domain.agent import capabilities
        uow = self._uow(owner_id)
        with uow.transaction():
            agents = uow.agents.list(filters={"team_id": team_id}, page_size=100).results
            selected = next((a for a in agents if a.role == role), None)
            if selected is None:
                return None, None
            skills, mcps = [], []
            for sid in selected.skill_ids:
                try:
                    skills.append(uow.skills.get(sid))
                except Exception:  # noqa: BLE001 - deleted grant: skip, don't fail
                    pass
            for mid in selected.mcp_server_ids:
                try:
                    mcps.append(uow.mcp_servers.get(mid))
                except Exception:  # noqa: BLE001
                    pass
            manifest = capabilities.assemble(selected, skills, mcps)
            if self._cipher is not None and selected.secret_ids:
                secret_env = {}
                for sec_id in selected.secret_ids:
                    try:
                        sec = uow.secrets.get(sec_id)
                        if sec.encrypted_value:
                            secret_env[sec.name] = self._cipher.decrypt(sec.encrypted_value)
                    except Exception:  # noqa: BLE001 - missing/bad secret: skip
                        pass
                manifest = manifest.model_copy(update={"secret_env": secret_env})
        return manifest, selected.role

    def _run_instructed_agent(self, payload, *, role, instructions, stage):
        """Run one agent with an explicit brief. Mirrors run_stage but selects the
        agent by `role` and drives it via RunContext.instructions. Returns a StageResult."""
        run_id = payload["run_id"]
        owner_id = payload["owner_id"]
        workspace_key = payload.get("workspace_key") or f"runs/{run_id}"
        workspace_path = self._storage.local_path(workspace_key)
        manifest, agent_role = self._manifest_for_role(owner_id, payload.get("team_id"), role)
        if manifest is not None:
            self._record_audit(
                owner_id, run_id, stage.value, agent_role.value if agent_role else "",
                {
                    "tools": list(manifest.allowed_tools),
                    "skills": [s.name for s in manifest.skills],
                    "mcp_servers": [m.name for m in manifest.mcp_servers],
                    "model_alias": manifest.model_alias,
                    "secret_count": len(manifest.secret_env),
                },
            )
        ctx = RunContext(
            run_id=run_id,
            stage=stage,
            task_title=payload["task_title"],
            acceptance_criteria=payload.get("acceptance_criteria", []),
            workspace_path=workspace_path,
            prior_artifacts=payload.get("prior_artifacts", {}),
            instructions=instructions,
            agent=manifest,
        )
        events = []
        for event in self._runtime.run_stage(ctx):
            events.append(event)
            _heartbeat(event.message)
            if event.type == "notification" and event.data.get("title"):
                self.record_notification({
                    "run_id": run_id, "owner_id": owner_id,
                    "category": event.data.get("category", "update"),
                    "severity": event.data.get("severity", "info"),
                    "title": event.data["title"],
                    "body": event.data.get("body", ""),
                })
            else:
                self.record_event({
                    "run_id": run_id, "owner_id": owner_id, "stage": stage.value,
                    "type": RunEventType.AGENT_EVENT, "message": event.message,
                })
        result = result_of(events)
        if result.model_usage:
            self.record_usage({
                "run_id": run_id, "owner_id": owner_id, "stage": stage.value,
                "agent_role": agent_role.value if agent_role else None,
                "model_usage": {m: u.model_dump() for m, u in result.model_usage.items()},
            })
        self._ingest_tool_audit(owner_id, run_id)
        return result

    def _read_artifact(self, run_id: str, name: str):
        """Read + json-decode an .orchestration artifact, or None if missing/invalid."""
        import json
        key = f"runs/{run_id}/.orchestration/{name}"
        if not self._storage.exists(key):
            return None
        text = self._storage.read_text(key)
        if not text.strip():
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return None

    def _persist_lead_messages(self, payload: dict, decision) -> None:
        """Persist the lead dispatches and notes as Messages so the inbox reflects
        orchestration. No-op when the lead agent id is unknown."""
        from domain.agent.models import AgentRole
        from domain.orchestration import decision_to_messages
        role_map = payload.get("role_to_agent_id") or {}
        lead_id = role_map.get(AgentRole.LEAD.value)
        if not lead_id:
            return
        msgs = decision_to_messages(
            decision, owner_id=payload["owner_id"], lead_agent_id=lead_id,
            run_id=payload["run_id"], work_item_id=payload.get("work_item_id"),
            project_id=payload.get("project_id"), role_to_agent_id=role_map,
        )
        if not msgs:
            return
        uow = self._uow(payload["owner_id"])
        with uow.transaction():
            for m in msgs:
                uow.messages.create(m)

    def _apply_lead_assignee(self, payload: dict, decision) -> None:
        """Persist the lead's assignee_role onto the work item (resolved via role map)."""
        from domain.orchestration import resolve_assignee
        role_map = payload.get("role_to_agent_id") or {}
        work_item_id = payload.get("work_item_id")
        agent_id = resolve_assignee(decision, role_map)
        if not work_item_id or not agent_id:
            return
        uow = self._uow(payload["owner_id"])
        with uow.transaction():
            item = uow.work_items.get(work_item_id)
            if item.assignee_agent_id != agent_id:
                uow.work_items.update(
                    work_item_id, item.model_copy(update={"assignee_agent_id": agent_id}))

    @activity.defn(name="invoke_lead")
    def invoke_lead(self, payload: dict) -> dict:
        from domain.agent.models import AgentRole
        from domain.orchestration import (
            OrchestrationContractError,
            OrchestrationState,
            build_orchestrator_prompt,
            parse_decision,
        )
        from domain.runs import RunStage
        run_id, owner_id = payload["run_id"], payload["owner_id"]
        state = OrchestrationState.model_validate(payload.get("state") or {})
        roles = [AgentRole(r) for r in payload.get("available_roles", [])]
        base_prompt = build_orchestrator_prompt(
            task_title=payload["task_title"],
            acceptance_criteria=payload.get("acceptance_criteria", []),
            body=payload.get("body", ""),
            state=state,
            available_roles=roles,
        )
        write_line = (
            "\n\nWrite your decision JSON (and nothing else) to the file "
            ".orchestration/decision.json in the workspace."
        )
        total_cost = 0.0
        hint = ""
        for _ in range(_MAX_LEAD_RETRIES + 1):
            result = self._run_instructed_agent(
                payload, role=AgentRole.LEAD,
                instructions=base_prompt + write_line + hint, stage=RunStage.PLAN,
            )
            total_cost += result.cost_usd
            raw = self._read_artifact(run_id, "decision.json")
            if raw is not None:
                try:
                    decision = parse_decision(raw)
                    self._persist_lead_messages(payload, decision)
                    self._apply_lead_assignee(payload, decision)
                    for d in decision.dispatches:
                        self.record_event({
                            "run_id": run_id, "owner_id": owner_id, "stage": "plan",
                            "type": RunEventType.AGENT_DISPATCHED,
                            "message": f"dispatch {d.target_role.value}",
                        })
                    return {"decision": decision.model_dump(mode="json"),
                            "cost_usd": total_cost}
                except OrchestrationContractError as exc:
                    hint = f"\n\nYour previous decision was invalid: {exc}. Try again."
            else:
                hint = "\n\nYou did not write a valid decision.json. Try again."
        return {"decision": {"intent": "block",
                             "rationale": "lead did not produce a valid decision"},
                "cost_usd": total_cost}

    @activity.defn(name="agent_step")
    def agent_step(self, payload: dict) -> dict:
        from domain.agent.memory import RoleMemoryEntry, role_memory_digest
        from domain.agent.models import AgentRole
        from domain.agent.prompts import memory_pointer
        from domain.orchestration import AgentOutcome, AgentStepResult, OutboundMessage
        from domain.runs import RunStage
        run_id, owner_id = payload["run_id"], payload["owner_id"]
        role = AgentRole(payload["role"]) if payload.get("role") else None
        digest = ""
        if role is not None:
            mem_filters = {"role": role.value}
            if payload.get("memory_scope") != "all" and payload.get("project_id"):
                mem_filters["project_id"] = payload["project_id"]
            mem_uow = self._uow(owner_id)
            with mem_uow.transaction():
                entries = mem_uow.role_memory.list(
                    filters=mem_filters, order_by="-created_at", page_size=20).results
            digest = role_memory_digest(entries, max_entries=15, max_chars=2000)
        instructions = (
            memory_pointer(role, digest)
            + f"{payload.get('incoming', '')}\n\nIf you need to message a teammate or the "
            "user, write a JSON list of outbound messages to .orchestration/outbox.json."
        )
        result = self._run_instructed_agent(
            payload, role=role, instructions=instructions, stage=RunStage.IMPLEMENT,
        )
        workspace_key = payload.get("workspace_key") or f"runs/{run_id}"
        learned = self._storage.read_text(f"{workspace_key}/.orchestration/role-memory.md")
        if role is not None and learned and learned.strip():
            try:
                rm_uow = self._uow(owner_id)
                with rm_uow.transaction():
                    rm_uow.role_memory.create(RoleMemoryEntry(
                        owner_id=owner_id, role=role, content=learned.strip(),
                        run_id=run_id, project_id=payload.get("project_id")))
            except Exception:  # noqa: BLE001 - role memory is advisory; never fail the stage
                pass
        outcome = AgentOutcome(result.outcome)
        outgoing = []
        raw = self._read_artifact(run_id, "outbox.json")
        if isinstance(raw, list):
            for item in raw:
                try:
                    outgoing.append(OutboundMessage.model_validate(item))
                except Exception:  # noqa: BLE001 - skip malformed outbound entries
                    pass
        self.record_event({
            "run_id": run_id, "owner_id": owner_id, "stage": "implement",
            "type": RunEventType.AGENT_REPORTED,
            "message": f"{payload.get('role', 'agent')} -> {outcome.value}",
        })
        return AgentStepResult(
            outcome=outcome,
            completed_brief=(outcome == AgentOutcome.OK),
            outgoing=outgoing,
            artifacts=result.artifacts,
            cost_usd=result.cost_usd,
        ).model_dump(mode="json")

    @activity.defn(name="run_monitor")
    def run_monitor(self, payload: dict) -> dict:
        from domain.agent.models import AgentRole
        from domain.orchestration import MonitorVerdict, OrchestrationContractError, parse_verdict
        from domain.runs import RunStage
        run_id, owner_id = payload["run_id"], payload["owner_id"]
        role = AgentRole(payload["role"]) if payload.get("role") else AgentRole.QA
        ac = "\n".join(f"- {c}" for c in payload.get("acceptance_criteria", []))
        instructions = (
            "Verify the task is complete against the acceptance criteria below. Write your "
            "verdict JSON (fields: complete, unmet[], pending_mailboxes[], notes) to "
            f".orchestration/verdict.json.\n\nAcceptance criteria:\n{ac}"
        )
        self.record_event({
            "run_id": run_id, "owner_id": owner_id, "stage": "verify",
            "type": RunEventType.MONITOR_STARTED, "message": "monitor started",
        })
        self._run_instructed_agent(
            payload, role=role, instructions=instructions, stage=RunStage.VERIFY,
        )
        raw = self._read_artifact(run_id, "verdict.json")
        verdict = MonitorVerdict(complete=False, notes="monitor produced no verdict")
        if raw is not None:
            try:
                verdict = parse_verdict(raw)
            except OrchestrationContractError:
                pass
        self.record_event({
            "run_id": run_id, "owner_id": owner_id, "stage": "verify",
            "type": RunEventType.MONITOR_VERDICT,
            "message": f"complete={verdict.complete}",
        })
        return verdict.model_dump(mode="json")

    @activity.defn(name="cleanup_workspace")
    def cleanup_workspace(self, payload: dict) -> None:
        self._storage.delete_directory(f"runs/{payload['run_id']}/")

    @activity.defn(name="reconcile_project_runs")
    def reconcile_project_runs(self, payload: dict) -> None:
        """Fill freed concurrency slots after a run ends. Best-effort: never raises."""
        try:
            uow = self._uow(payload["owner_id"])
            with uow.transaction():
                run_inputs = reconcile_project(uow, self._settings, payload["project_id"])
            for ri in run_inputs:
                self._run_client.start_run_workflow(ri, "OrchestratorWorkflow")
        except Exception:  # noqa: BLE001 - scheduling must never fail run completion
            pass

    @activity.defn(name="provision_workspace")
    def provision_workspace(self, payload: dict) -> dict:
        run_id = payload["run_id"]
        workspace = self._storage.local_path(f"runs/{run_id}")
        token = self._forge.installation_token() if payload["profile"] == "remote" else None
        mode = "clone" if payload["profile"] == "remote" else "worktree"
        # Remote: worktree off origin/<base> in the cache. Local: base stays HEAD.
        base = payload.get("base") if mode == "clone" else None
        self._git.prepare(repo_ref=payload["repo_ref"], workspace_path=workspace,
                          branch=payload["branch"], mode=mode, base=base, token=token)
        self.record_event({"run_id": run_id, "owner_id": payload["owner_id"],
                           "stage": "provision", "type": "stage_completed",
                           "message": f"workspace ready on {payload['branch']}"})
        return {"outcome": "ok"}

    @activity.defn(name="provision_engineer_workspace")
    def provision_engineer_workspace(self, payload: dict) -> dict:
        workspace = self._storage.local_path(payload["workspace_key"])
        self._git.prepare(repo_ref=payload["repo_ref"], workspace_path=workspace,
                          branch=payload["branch"], mode="worktree", base=payload["base"])
        self.record_event({"run_id": payload["run_id"], "owner_id": payload["owner_id"],
                           "stage": "implement", "type": "stage_started",
                           "message": f"engineer workspace {payload['branch']}"})
        return {"outcome": "ok"}

    @activity.defn(name="integrate_branches")
    def integrate_branches(self, payload: dict) -> dict:
        workspace = self._storage.local_path(payload["workspace_key"])
        merged: list[str] = []
        for branch in payload["branches"]:
            result = self._git.merge_branch(workspace, branch=branch)
            if not result.ok:
                msg = f"merge conflict on {branch}: {result.conflict_files}"
                self.record_event({"run_id": payload["run_id"], "owner_id": payload["owner_id"],
                                   "stage": "implement", "type": "agent_reported", "message": msg})
                return {"merged": merged,
                        "conflict": {"branch": branch, "files": result.conflict_files}}
            merged.append(branch)
            self.record_event({"run_id": payload["run_id"], "owner_id": payload["owner_id"],
                               "stage": "implement", "type": "agent_reported",
                               "message": f"merged {branch}"})
        return {"merged": merged, "conflict": None}

    @activity.defn(name="commit_engineer_branch")
    def commit_engineer_branch(self, payload: dict) -> bool:
        workspace = self._storage.local_path(payload["workspace_key"])
        return self._git.commit_all(workspace, payload["title"], exclude=WORKSPACE_SCRATCH)

    @activity.defn(name="open_pr")
    def open_pr(self, payload: dict) -> dict:
        run_id, owner_id = payload["run_id"], payload["owner_id"]
        workspace = self._storage.local_path(f"runs/{run_id}")
        self._git.commit_all(workspace, payload["title"], exclude=WORKSPACE_SCRATCH)
        if not self._git.has_commits_ahead(workspace, payload["base"]):
            self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "pr",
                               "type": "stage_completed", "message": "no changes to PR"})
            return {"outcome": "ok", "pr_url": None}
        if payload["profile"] == "remote":
            token = self._forge.installation_token()
            self._git.push(workspace, payload["branch"], token=token)
            pr_url = self._forge.open_pull_request(
                head=payload["branch"], base=payload["base"],
                title=payload["title"], body=payload["body"])
            self.persist_run_state({"run_id": run_id, "owner_id": owner_id,
                                    "branch": payload["branch"], "pr_url": pr_url})
            self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "pr",
                               "type": "stage_completed", "message": f"opened {pr_url}"})
            return {"outcome": "ok", "pr_url": pr_url}
        # local profile: record the branch, no push/PR
        self.persist_run_state({"run_id": run_id, "owner_id": owner_id,
                                "branch": payload["branch"]})
        self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "pr",
                           "type": "stage_completed",
                           "message": f"branch {payload['branch']} ready"})
        return {"outcome": "ok", "pr_url": None}

    @activity.defn(name="capture_memory")
    def capture_memory(self, payload: dict) -> dict:
        from domain.agent.memory import MEMORY_PATHS, MemoryProposal, changed_files
        run_id, owner_id = payload["run_id"], payload["owner_id"]
        workspace = self._storage.local_path(f"runs/{run_id}")
        diff = self._git.diff(workspace, paths=MEMORY_PATHS)
        if not diff.strip():
            self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "learn",
                               "type": RunEventType.AGENT_EVENT,
                               "message": "no memory changes"})
            return {"outcome": "ok", "proposal_id": None}
        branch = f"agent/memory-{run_id}"
        committed = self._git.commit_to_branch(
            workspace, branch=branch, base=payload["base"], paths=MEMORY_PATHS,
            message=f"chore: memory update for run {run_id}")
        if committed and payload["profile"] == "remote":
            try:
                token = self._forge.installation_token()
                self._git.push(workspace, branch, token=token)
            except Exception:  # noqa: BLE001 - push is best-effort; the proposal still persists
                pass
        files = changed_files(diff)
        uow = self._uow(owner_id)
        with uow.transaction():
            proposal = uow.memory_proposals.create(MemoryProposal(
                owner_id=owner_id, run_id=run_id, project_id=payload["project_id"],
                branch=branch, diff=diff, files=files))
        self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "learn",
                           "type": RunEventType.AGENT_EVENT,
                           "message": f"memory proposal: {len(files)} file(s) on {branch}"})
        if payload.get("autonomy") == "full_auto":
            self._auto_apply_memory(payload, proposal)
        return {"outcome": "ok", "proposal_id": proposal.id}

    @activity.defn(name="curate_memory")
    def curate_memory(self, payload: dict) -> dict:
        """Run the LEARN curator (generic role -> Read/Edit/Write) in the main run worktree to
        update project memory. Advisory: a curator failure never fails the run."""
        from domain.agent.prompts import for_stage
        from domain.runs import RunStage
        learn_prompt, _tools = for_stage(
            RunStage.LEARN, payload["task_title"],
            payload.get("acceptance_criteria", []), payload.get("body", ""))
        try:
            self._run_instructed_agent(
                payload, role=None, instructions=learn_prompt, stage=RunStage.LEARN)
        except Exception:  # noqa: BLE001 - curation is advisory; never fail the run
            pass
        return {"outcome": "ok"}

    def _auto_apply_memory(self, payload: dict, proposal) -> None:
        from interactors.cli.memory_apply import MemoryApplier
        run_id, owner_id = payload["run_id"], payload["owner_id"]
        try:
            applier = MemoryApplier(self._git, self._forge, profile=payload["profile"])
            applied = applier.apply(proposal, repo_ref=payload["repo_ref"],
                                    base=payload["base"])
            with self._uow(owner_id).transaction() as uow:
                uow.memory_proposals.update(proposal.id, applied)
            msg = (f"memory PR opened {applied.pr_url}" if applied.pr_url
                   else f"memory applied to {payload['base']}")
            self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "learn",
                               "type": RunEventType.AGENT_EVENT, "message": msg})
        except Exception as exc:  # noqa: BLE001 - auto-apply is best-effort; stays proposed
            self.record_event({"run_id": run_id, "owner_id": owner_id, "stage": "learn",
                               "type": RunEventType.AGENT_EVENT,
                               "message": f"memory auto-apply failed: {exc}"})
