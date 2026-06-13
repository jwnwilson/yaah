from temporalio import activity

from adapters.database.uow import SqlUnitOfWork
from adapters.notify.ports import NotificationDispatcher
from adapters.runtime.fake import result_of
from adapters.storage.ports import StoragePort
from domain.models import (
    Notification,
    NotificationCategory,
    NotificationSeverity,
    NotificationSource,
    RunEvent,
    RunEventType,
    RunStage,
    RunStatus,
    utc_now,
)
from domain.notifications import notification_for_event, resolves
from domain.runtime import AgentRuntime, RunContext


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
                 notifier: NotificationDispatcher | None = None) -> None:
        self._session_factory = session_factory
        self._runtime = runtime
        self._storage = storage
        self._git = git
        self._forge = forge
        self._cipher = cipher
        self._notifier = notifier or NotificationDispatcher([])

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

    @activity.defn(name="run_stage")
    def run_stage(self, payload: dict) -> dict:
        workspace_path = self._storage.local_path(f"runs/{payload['run_id']}")

        agent_manifest = None
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
            if event.type == "notification" and event.data.get("title"):
                self.record_notification(
                    {
                        "run_id": payload["run_id"],
                        "owner_id": payload["owner_id"],
                        "category": event.data.get("category", "update"),
                        "severity": event.data.get("severity", "info"),
                        "title": event.data["title"],
                        "body": event.data.get("body", ""),
                    }
                )
            else:
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
