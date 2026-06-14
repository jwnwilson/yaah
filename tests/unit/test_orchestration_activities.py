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
