import json

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.storage.local import LocalStorageAdapter
from domain.agent import AgentEvent, StageResult
from domain.models import (
    MessageKind,
    MessageRecipientKind,
    MessageSenderKind,
    Project,
    Run,
    RunStage,
    WorkItem,
    WorkItemKind,
    WorkItemStatus,
)


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _seed_run(factory, run_id="r1", owner_id="dev-user"):
    """Seed project/feature/task/run so record_event + record_usage have rows to read."""
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": owner_id})
    with uow.transaction():
        uow.projects.create(Project(id="p1", owner_id=owner_id, name="P", local_path="/tmp/x"))
        uow.work_items.create(WorkItem(id="e1", owner_id=owner_id, project_id="p1",
                                       kind=WorkItemKind.EPIC, parent_id=None, title="E"))
        uow.work_items.create(WorkItem(id="f1", owner_id=owner_id, project_id="p1",
                                       kind=WorkItemKind.FEATURE, parent_id="e1", title="F"))
        uow.work_items.create(WorkItem(id="t1", owner_id=owner_id, project_id="p1",
                                       kind=WorkItemKind.TASK, parent_id="f1", title="T",
                                       status=WorkItemStatus.IN_PROGRESS))
        uow.runs.create(Run(id=run_id, owner_id=owner_id, task_id="t1", team_id="tm1"))


def _acts(factory, runtime=None, storage=None):
    # build a minimal RunActivities; only session_factory + runtime + storage are exercised
    from interactors.temporal.activities import RunActivities
    return RunActivities(factory, runtime, storage=storage, git=None, forge=None)


def _msg_dict():
    return dict(
        owner_id="dev-user", sender_kind=MessageSenderKind.AGENT, sender_agent_id="a-lead",
        recipient_kind=MessageRecipientKind.AGENT, recipient_agent_id="a-eng",
        kind=MessageKind.DISPATCH, body="go", run_id="r1",
    )


# ---------------------------------------------------------------------------
# Task 1: persist_messages
# ---------------------------------------------------------------------------
def test_persist_messages_writes_rows():
    factory = _factory()
    acts = _acts(factory)
    acts.persist_messages({"owner_id": "dev-user", "messages": [_msg_dict()]})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        assert uow.messages.list().total == 1


def test_persist_messages_is_idempotent_on_id():
    factory = _factory()
    acts = _acts(factory)
    from domain.models import Message
    m = Message(**_msg_dict())
    acts.persist_messages({"owner_id": "dev-user", "messages": [m.model_dump(mode="json")]})
    acts.persist_messages({"owner_id": "dev-user", "messages": [m.model_dump(mode="json")]})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        assert uow.messages.list().total == 1


# ---------------------------------------------------------------------------
# Task 2: _run_instructed_agent
# ---------------------------------------------------------------------------
def test_run_instructed_agent_passes_instructions_and_returns_result(tmp_path):
    class StubRuntime:
        def __init__(self):
            self.ctx = None

        def run_stage(self, ctx):
            self.ctx = ctx
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok", cost_usd=0.1).model_dump())

        def cancel(self, run_id): ...

    factory = _factory()
    _seed_run(factory)
    rt = StubRuntime()
    acts = _acts(factory, runtime=rt, storage=LocalStorageAdapter(base_dir=str(tmp_path)))
    result = acts._run_instructed_agent(
        {"run_id": "r1", "owner_id": "dev-user", "task_title": "t",
         "acceptance_criteria": ["c"], "team_id": None},
        role=None, instructions="BRIEF", stage=RunStage.IMPLEMENT,
    )
    assert rt.ctx.instructions == "BRIEF"
    assert rt.ctx.stage == RunStage.IMPLEMENT
    assert result.outcome == "ok"


# ---------------------------------------------------------------------------
# helpers for file-transport stub runtimes
# ---------------------------------------------------------------------------
def _writing_runtime(storage, filename, body):
    """A stub runtime whose run_stage writes `body` (a dict) as JSON to the
    `.orchestration/<filename>` artifact before yielding its result event."""

    class StubRuntime:
        def run_stage(self, ctx):
            storage.write_bytes(
                f"runs/{ctx.run_id}/.orchestration/{filename}",
                json.dumps(body).encode(),
            )
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok", cost_usd=0.2).model_dump())

        def cancel(self, run_id): ...

    return StubRuntime()


# ---------------------------------------------------------------------------
# Task 3: invoke_lead
# ---------------------------------------------------------------------------
def test_invoke_lead_returns_parsed_continue_decision(tmp_path):
    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    decision = {
        "intent": "continue",
        "dispatches": [
            {"target_role": "backend", "instructions": "build it", "acceptance": ["a"]}
        ],
        "rationale": "start the work",
    }
    rt = _writing_runtime(storage, "decision.json", decision)
    factory = _factory()
    _seed_run(factory)
    acts = _acts(factory, runtime=rt, storage=storage)
    out = acts.invoke_lead({
        "run_id": "r1", "owner_id": "dev-user", "task_title": "t",
        "acceptance_criteria": ["c"], "body": "do the thing", "team_id": None,
        "available_roles": ["backend", "qa"], "state": {},
    })
    assert out["decision"]["intent"] == "continue"
    assert out["decision"]["dispatches"][0]["target_role"] == "backend"
    assert out["cost_usd"] == 0.2


def test_invoke_lead_blocks_when_no_valid_decision(tmp_path):
    storage = LocalStorageAdapter(base_dir=str(tmp_path))

    class StubRuntime:
        def run_stage(self, ctx):
            # never writes decision.json
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok", cost_usd=0.1).model_dump())

        def cancel(self, run_id): ...

    factory = _factory()
    _seed_run(factory)
    acts = _acts(factory, runtime=StubRuntime(), storage=storage)
    out = acts.invoke_lead({
        "run_id": "r1", "owner_id": "dev-user", "task_title": "t",
        "acceptance_criteria": ["c"], "body": "", "team_id": None,
        "available_roles": ["backend"], "state": {},
    })
    assert out["decision"]["intent"] == "block"


# ---------------------------------------------------------------------------
# Task 4: agent_step
# ---------------------------------------------------------------------------
def test_agent_step_reports_outbox_and_completion(tmp_path):
    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    outbox = [
        {"recipient_kind": "agent", "recipient_role": "qa", "kind": "chat",
         "subject": "", "body": "please review"}
    ]
    rt = _writing_runtime(storage, "outbox.json", outbox)
    factory = _factory()
    _seed_run(factory)
    acts = _acts(factory, runtime=rt, storage=storage)
    out = acts.agent_step({
        "run_id": "r1", "owner_id": "dev-user", "task_title": "t",
        "acceptance_criteria": ["c"], "role": "backend", "incoming": "do work",
        "team_id": None,
    })
    assert out["completed_brief"] is True
    assert out["outcome"] == "ok"
    assert len(out["outgoing"]) == 1
    assert out["outgoing"][0]["recipient_role"] == "qa"


def test_agent_step_without_outbox_has_no_outgoing(tmp_path):
    storage = LocalStorageAdapter(base_dir=str(tmp_path))

    class StubRuntime:
        def run_stage(self, ctx):
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok", cost_usd=0.1).model_dump())

        def cancel(self, run_id): ...

    factory = _factory()
    _seed_run(factory)
    acts = _acts(factory, runtime=StubRuntime(), storage=storage)
    out = acts.agent_step({
        "run_id": "r1", "owner_id": "dev-user", "task_title": "t",
        "acceptance_criteria": ["c"], "role": "backend", "incoming": "do work",
        "team_id": None,
    })
    assert out["outgoing"] == []
    assert out["completed_brief"] is True


# ---------------------------------------------------------------------------
# Task 5: run_monitor
# ---------------------------------------------------------------------------
def test_run_monitor_returns_complete_verdict(tmp_path):
    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    verdict = {"complete": True, "unmet": [], "notes": "all good"}
    rt = _writing_runtime(storage, "verdict.json", verdict)
    factory = _factory()
    _seed_run(factory)
    acts = _acts(factory, runtime=rt, storage=storage)
    out = acts.run_monitor({
        "run_id": "r1", "owner_id": "dev-user", "task_title": "t",
        "acceptance_criteria": ["c"], "team_id": None,
    })
    assert out["complete"] is True
    assert out["notes"] == "all good"


def test_run_monitor_incomplete_when_no_verdict(tmp_path):
    storage = LocalStorageAdapter(base_dir=str(tmp_path))

    class StubRuntime:
        def run_stage(self, ctx):
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok", cost_usd=0.1).model_dump())

        def cancel(self, run_id): ...

    factory = _factory()
    _seed_run(factory)
    acts = _acts(factory, runtime=StubRuntime(), storage=storage)
    out = acts.run_monitor({
        "run_id": "r1", "owner_id": "dev-user", "task_title": "t",
        "acceptance_criteria": ["c"], "team_id": None,
    })
    assert out["complete"] is False


def test_ingest_tool_audit_is_idempotent(tmp_path):
    from interactors.temporal.activities import RunActivities

    factory = _factory()
    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    storage.write_bytes(
        "runs/r1/audit.jsonl",
        b'{"tool":"Read","decision":"allow"}\n{"tool":"Bash","decision":"deny"}\n',
    )
    acts = RunActivities(factory, None, storage, None, None)
    acts._ingest_tool_audit("u1", "r1")
    acts._ingest_tool_audit("u1", "r1")  # file consumed -> no double-count
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        assert uow.audit_events.list(filters={"run_id": "r1"}).total == 2


# ---------------------------------------------------------------------------
# Capability composition + audit + notifications via the agent_step path
# (migrated from the removed run_stage activity — these behaviors now ride
# _run_instructed_agent, which every orchestrator agent turn goes through).
# ---------------------------------------------------------------------------
class _ResultSpy:
    """Runtime that captures ctx and yields a single ok result event."""

    def __init__(self):
        self.ctx = None

    def run_stage(self, ctx):
        self.ctx = ctx
        yield AgentEvent(type="result", stage=ctx.stage,
                         data=StageResult(outcome="ok").model_dump())

    def cancel(self, run_id): ...


def _agent_step(acts, team_id, role="backend"):
    return acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": role,
                            "incoming": "do it", "task_title": "T",
                            "acceptance_criteria": [], "team_id": team_id})


def test_agent_step_populates_manifest_from_team(tmp_path):
    from domain.models import AgentDefinition, Skill, Team

    factory = _factory()
    _seed_run(factory)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="dev-user", name="T"))
        sk = uow.skills.create(Skill(owner_id="dev-user", name="pytest", source="git@x/s.git"))
        uow.agents.create(AgentDefinition(
            team_id=team.id, role="backend", name="Eng", model_alias="m",
            system_prompt="build", allowed_tools=["Read", "Edit"], skill_ids=[sk.id]))
    spy = _ResultSpy()
    acts = _acts(factory, runtime=spy, storage=LocalStorageAdapter(base_dir=str(tmp_path)))
    _agent_step(acts, team.id)
    assert spy.ctx.agent is not None
    assert spy.ctx.agent.system_prompt == "build"
    assert spy.ctx.agent.allowed_tools == ["Read", "Edit"]
    assert spy.ctx.agent.skills[0].source == "git@x/s.git"


def test_agent_step_injects_secret_env_without_leaking(tmp_path):
    from cryptography.fernet import Fernet

    from domain.models import AgentDefinition, Secret, Team
    from interactors.temporal.activities import RunActivities
    from lib.secrets import FernetCipher

    factory = _factory()
    _seed_run(factory)
    cipher = FernetCipher(Fernet.generate_key().decode())
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="dev-user", name="T"))
        sec = uow.secrets.create(Secret(owner_id="dev-user", name="GH_TOKEN",
                                        encrypted_value=cipher.encrypt("ghp_TOPSECRET")))
        uow.agents.create(AgentDefinition(team_id=team.id, role="backend", name="E",
                                          model_alias="m", secret_ids=[sec.id]))
    spy = _ResultSpy()
    recorded = []
    acts = RunActivities(factory, spy, LocalStorageAdapter(base_dir=str(tmp_path)),
                         None, None, cipher=cipher)
    orig = acts.record_event
    acts.record_event = lambda p: recorded.append(p) or orig(p)
    result = _agent_step(acts, team.id)
    # security invariant: plaintext injected in-process, never in output or events
    assert spy.ctx.agent.secret_env == {"GH_TOKEN": "ghp_TOPSECRET"}
    assert "ghp_TOPSECRET" not in json.dumps(result)
    assert "ghp_TOPSECRET" not in json.dumps(recorded)


def test_agent_step_records_capability_audit_without_secret_values(tmp_path):
    from cryptography.fernet import Fernet

    from domain.models import AgentDefinition, Secret, Team
    from interactors.temporal.activities import RunActivities
    from lib.secrets import FernetCipher

    factory = _factory()
    _seed_run(factory)
    cipher = FernetCipher(Fernet.generate_key().decode())
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="dev-user", name="T"))
        sec = uow.secrets.create(Secret(owner_id="dev-user", name="GH",
                                        encrypted_value=cipher.encrypt("ghp_SECRET")))
        uow.agents.create(AgentDefinition(
            team_id=team.id, role="backend", name="E", model_alias="engineer-model",
            allowed_tools=["Read", "Edit"], secret_ids=[sec.id]))
    acts = RunActivities(factory, _ResultSpy(), LocalStorageAdapter(base_dir=str(tmp_path)),
                         None, None, cipher=cipher)
    _agent_step(acts, team.id)
    uow2 = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow2.transaction():
        granted = [e for e in uow2.audit_events.list(filters={"run_id": "r1"}).results
                   if e.action == "capability_granted"]
    assert len(granted) == 1
    detail = granted[0].detail
    assert detail["tools"] == ["Read", "Edit"]
    assert detail["model_alias"] == "engineer-model"
    assert detail["secret_count"] == 1
    assert "ghp_SECRET" not in json.dumps(detail)  # no secret value in the audit


def test_agent_step_ingests_tool_audit_jsonl(tmp_path):
    from domain.models import AgentDefinition, Team
    from interactors.temporal.activities import RunActivities

    factory = _factory()
    _seed_run(factory)
    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="dev-user", name="T"))
        uow.agents.create(AgentDefinition(team_id=team.id, role="backend", name="E",
                                          model_alias="m", allowed_tools=["Read"]))

    class _AuditSpy:
        def __init__(self, s):
            self._s = s

        def run_stage(self, ctx):
            self._s.write_bytes(
                f"runs/{ctx.run_id}/audit.jsonl",
                (json.dumps({"tool": "Read", "decision": "allow", "reason": "granted"}) + "\n"
                 + json.dumps({"tool": "Bash", "decision": "deny",
                               "reason": "not in allowlist"}) + "\n").encode())
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok").model_dump())

        def cancel(self, run_id): ...

    acts = RunActivities(factory, _AuditSpy(storage), storage, None, None)
    _agent_step(acts, team.id)
    uow2 = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow2.transaction():
        evs = uow2.audit_events.list(filters={"run_id": "r1"}).results
    actions = sorted(e.action for e in evs if e.action in ("tool_allowed", "tool_denied"))
    assert actions == ["tool_allowed", "tool_denied"]
    denied = [e for e in evs if e.action == "tool_denied"][0]
    assert denied.detail["tool"] == "Bash"  # detail carries tool + reason only, no inputs


def test_agent_step_records_agent_raised_notification(tmp_path):
    """A `notification` agent event (the yaah_notify capability) becomes an in-app
    Notification on the orchestrator path, same as the old run_stage path did."""
    factory = _factory()
    _seed_run(factory)

    class _NotifySpy:
        def run_stage(self, ctx):
            yield AgentEvent(type="notification", stage=ctx.stage, message="flag",
                             data={"title": "Need a decision", "category": "decision",
                                   "severity": "attention", "body": "which db?"})
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok").model_dump())

        def cancel(self, run_id): ...

    acts = _acts(factory, runtime=_NotifySpy(),
                 storage=LocalStorageAdapter(base_dir=str(tmp_path)))
    _agent_step(acts, team_id=None)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        notifs = uow.notifications.list(filters={"run_id": "r1"}).results
    assert len(notifs) == 1
    assert notifs[0].title == "Need a decision"
    assert notifs[0].category == "decision"
    assert notifs[0].source == "agent"


def test_agent_step_uses_custom_workspace_key(tmp_path):
    factory = _factory()
    _seed_run(factory)
    spy = _ResultSpy()
    from adapters.storage.local import LocalStorageAdapter
    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    acts = _acts(factory, runtime=spy, storage=storage)
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend",
                     "incoming": "do it", "task_title": "T", "acceptance_criteria": [],
                     "team_id": None, "workspace_key": "runs/r1/w/backend-1-0"})
    assert spy.ctx.workspace_path.endswith("runs/r1/w/backend-1-0")


def test_agent_step_injects_role_digest_project_default_and_all(tmp_path):
    from adapters.database.uow import SqlUnitOfWork
    from adapters.storage.local import LocalStorageAdapter
    from domain.models import AgentRole, RoleMemoryEntry
    factory = _factory()
    _seed_run(factory)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="this-project note", project_id="p1"))
        uow.role_memory.create(RoleMemoryEntry(owner_id="dev-user", role=AgentRole.BACKEND,
                                               content="other-project note", project_id="p2"))
    spy = _ResultSpy()
    acts = _acts(factory, runtime=spy, storage=LocalStorageAdapter(base_dir=str(tmp_path)))
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend", "incoming": "do",
                     "task_title": "T", "acceptance_criteria": [], "team_id": None,
                     "project_id": "p1"})
    assert "this-project note" in spy.ctx.instructions
    assert "other-project note" not in spy.ctx.instructions
    assert "CLAUDE.md" in spy.ctx.instructions
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend", "incoming": "do",
                     "task_title": "T", "acceptance_criteria": [], "team_id": None,
                     "project_id": "p1", "memory_scope": "all"})
    assert "other-project note" in spy.ctx.instructions
    assert "this-project note" in spy.ctx.instructions  # 'all' is a superset


def test_agent_step_persists_authored_role_memory(tmp_path):
    from adapters.database.uow import SqlUnitOfWork
    from adapters.storage.local import LocalStorageAdapter
    factory = _factory()
    _seed_run(factory)
    storage = LocalStorageAdapter(base_dir=str(tmp_path))

    class _Author:
        def run_stage(self, ctx):
            from domain.agent import AgentEvent, StageResult
            storage.write_bytes("runs/r1/.orchestration/role-memory.md",
                                b"Keep migrations reversible.")
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok").model_dump())
        def cancel(self, run_id): ...

    acts = _acts(factory, runtime=_Author(), storage=storage)
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend", "incoming": "do",
                     "task_title": "T", "acceptance_criteria": [], "team_id": None,
                     "project_id": "p1"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        rows = uow.role_memory.list(filters={"role": "backend"}).results
    assert len(rows) == 1
    assert rows[0].content == "Keep migrations reversible."
    assert rows[0].project_id == "p1" and rows[0].run_id == "r1"


def test_agent_step_persists_role_memory_from_instance_workspace(tmp_path):
    from adapters.database.uow import SqlUnitOfWork
    from adapters.storage.local import LocalStorageAdapter
    factory = _factory()
    _seed_run(factory)
    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    ws_key = "runs/r1/.yaah-eng/backend-1-0"  # a parallel-engineer instance worktree

    class _Author:
        def run_stage(self, ctx):
            from domain.agent import AgentEvent, StageResult
            storage.write_bytes(f"{ws_key}/.orchestration/role-memory.md", b"note from instance")
            yield AgentEvent(type="result", stage=ctx.stage,
                             data=StageResult(outcome="ok").model_dump())
        def cancel(self, run_id): ...

    acts = _acts(factory, runtime=_Author(), storage=storage)
    acts.agent_step({"run_id": "r1", "owner_id": "dev-user", "role": "backend", "incoming": "do",
                     "task_title": "T", "acceptance_criteria": [], "team_id": None,
                     "project_id": "p1", "workspace_key": ws_key})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "dev-user"})
    with uow.transaction():
        rows = uow.role_memory.list(filters={"role": "backend"}).results
    assert len(rows) == 1 and rows[0].content == "note from instance"
