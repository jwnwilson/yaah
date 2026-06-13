from temporalio import activity

from adapters.database.uow import SqlUnitOfWork
from adapters.runtime.fake import result_of
from adapters.storage.ports import StoragePort
from domain.errors import IntegrityConflict
from domain.models import (
    AgentRole,
    RunEvent,
    RunEventType,
    RunStage,
    RunStatus,
    UsageRecord,
    utc_now,
)
from domain.runtime import AgentRuntime, RunContext
from domain.usage import TokenUsage


def _heartbeat(detail: str) -> None:
    try:
        activity.heartbeat(detail)
    except RuntimeError:
        pass  # not running inside a Temporal activity (unit test)


class RunActivities:
    """Holds the session factory, runtime, storage, git, and forge; exposes Temporal activities.
    The ONLY DB writer during a run."""

    def __init__(self, session_factory, runtime: AgentRuntime, storage: StoragePort,
                 git, forge, *, cipher=None) -> None:
        self._session_factory = session_factory
        self._runtime = runtime
        self._storage = storage
        self._git = git
        self._forge = forge
        self._cipher = cipher

    def _uow(self, owner_id: str) -> SqlUnitOfWork:
        return SqlUnitOfWork(self._session_factory, required_filters={"owner_id": owner_id})

    def _record_audit(
        self, owner_id: str, run_id: str, stage: str, actor: str, detail: dict
    ) -> None:
        from domain.models import AuditAction, AuditEvent, RunStage, utc_now
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

    @activity.defn(name="run_stage")
    def run_stage(self, payload: dict) -> dict:
        workspace_path = self._storage.local_path(f"runs/{payload['run_id']}")

        agent_manifest = None
        agent_role = None
        team_id = payload.get("team_id")
        if team_id:
            from domain import capabilities
            uow = self._uow(payload["owner_id"])
            with uow.transaction():
                agents = uow.agents.list(filters={"team_id": team_id}, page_size=100).results
                selected = capabilities.select_agent(agents, RunStage(payload["stage"]))
                if selected is not None:
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
                    agent_manifest = capabilities.assemble(selected, skills, mcps)
                    agent_role = selected.role
                    if self._cipher is not None and selected.secret_ids:
                        secret_env = {}
                        for sec_id in selected.secret_ids:
                            try:
                                sec = uow.secrets.get(sec_id)
                                if sec.encrypted_value:
                                    secret_env[sec.name] = self._cipher.decrypt(sec.encrypted_value)
                            except Exception:  # noqa: BLE001 - missing/bad secret: skip, don't fail
                                pass
                        agent_manifest = agent_manifest.model_copy(
                            update={"secret_env": secret_env}
                        )

        if agent_manifest is not None:
            self._record_audit(
                payload["owner_id"], payload["run_id"], payload["stage"],
                selected.role,
                {
                    "tools": list(agent_manifest.allowed_tools),
                    "skills": [s.name for s in agent_manifest.skills],
                    "mcp_servers": [m.name for m in agent_manifest.mcp_servers],
                    "model_alias": agent_manifest.model_alias,
                    "secret_count": len(agent_manifest.secret_env),
                },
            )

        ctx = RunContext(
            run_id=payload["run_id"],
            stage=RunStage(payload["stage"]),
            task_title=payload["task_title"],
            acceptance_criteria=payload.get("acceptance_criteria", []),
            workspace_path=workspace_path,
            prior_artifacts=payload.get("prior_artifacts", {}),
            agent=agent_manifest,
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
        result = result_of(events)
        if result.model_usage:
            self.record_usage({
                "run_id": payload["run_id"], "owner_id": payload["owner_id"],
                "stage": payload["stage"],
                "agent_role": agent_role.value if agent_role else None,
                "model_usage": {m: u.model_dump() for m, u in result.model_usage.items()},
            })
        return result.model_dump()

    @activity.defn(name="cleanup_workspace")
    def cleanup_workspace(self, payload: dict) -> None:
        self._storage.delete_directory(f"runs/{payload['run_id']}/")

    @activity.defn(name="provision_workspace")
    def provision_workspace(self, payload: dict) -> dict:
        run_id = payload["run_id"]
        workspace = self._storage.local_path(f"runs/{run_id}")
        token = self._forge.installation_token() if payload["profile"] == "remote" else None
        mode = "clone" if payload["profile"] == "remote" else "worktree"
        self._git.prepare(repo_ref=payload["repo_ref"], workspace_path=workspace,
                          branch=payload["branch"], mode=mode, token=token)
        self.record_event({"run_id": run_id, "owner_id": payload["owner_id"],
                           "stage": "provision", "type": "stage_completed",
                           "message": f"workspace ready on {payload['branch']}"})
        return {"outcome": "ok"}

    @activity.defn(name="open_pr")
    def open_pr(self, payload: dict) -> dict:
        run_id, owner_id = payload["run_id"], payload["owner_id"]
        workspace = self._storage.local_path(f"runs/{run_id}")
        committed = self._git.commit_all(workspace, payload["title"])
        if not committed:
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
