import tempfile

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.database.uow import SqlUnitOfWork
from adapters.forge.fake import FakeGitForge
from adapters.git.fake import FakeGit
from adapters.runtime.fake import FakeAgentRuntime
from adapters.storage.local import LocalStorageAdapter
from domain.models import Run, RunStage, RunStatus
from interactors.temporal.activities import RunActivities


def _factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _storage():
    return LocalStorageAdapter(base_dir=tempfile.mkdtemp())


def _seed_run(factory) -> str:
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.create(Run(owner_id="u1", task_id="t1", team_id="tm1"))
    return run.id


def _acts(factory, *, git=None, forge=None, has_changes=True):
    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    return RunActivities(factory, FakeAgentRuntime(storage=storage), storage,
                         git or FakeGit(has_changes=has_changes), forge or FakeGitForge())


def test_persist_run_state_updates_row():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = _acts(factory)
    acts.persist_run_state(
        {
            "run_id": run_id,
            "owner_id": "u1",
            "status": RunStatus.RUNNING,
            "stage": RunStage.PLAN,
            "cost_usd": 1.0,
        }
    )
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.status == "running" and run.stage == "plan" and run.cost_usd == 1.0


def test_run_stage_records_events_and_returns_result():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = _acts(factory)
    result = acts.run_stage(
        {
            "run_id": run_id,
            "owner_id": "u1",
            "stage": RunStage.PLAN,
            "task_title": "T",
            "acceptance_criteria": [],
        }
    )
    assert result["outcome"] == "ok"
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        page = uow.run_events.list(filters={"run_id": run_id})
    assert page.total >= 1


def test_cleanup_workspace_deletes_run_dir():
    factory = _factory()
    storage = _storage()
    storage.write_bytes("runs/r1/plan.md", b"data")
    assert storage.exists("runs/r1/plan.md")
    acts = RunActivities(factory, FakeAgentRuntime(), storage, FakeGit(), FakeGitForge())
    acts.cleanup_workspace({"run_id": "r1", "owner_id": "u1"})
    assert not storage.exists("runs/r1")


def test_persist_sets_branch_and_pr_url():
    factory = _factory()
    run_id = _seed_run(factory)
    acts = _acts(factory)
    acts.persist_run_state({"run_id": run_id, "owner_id": "u1",
                            "branch": "agent/x", "pr_url": "https://github.com/o/r/pull/1"})
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.branch == "agent/x"
    assert run.pr_url == "https://github.com/o/r/pull/1"


def test_provision_calls_git_prepare():
    factory = _factory()
    run_id = _seed_run(factory)
    git = FakeGit()
    acts = _acts(factory, git=git)
    acts.provision_workspace({"run_id": run_id, "owner_id": "u1", "profile": "local",
                              "repo_ref": "/repo", "branch": "agent/t1"})
    assert git.prepared and git.prepared[0][2] == "agent/t1"


def test_open_pr_remote_pushes_and_records_pr_url():
    factory = _factory()
    run_id = _seed_run(factory)
    git, forge = FakeGit(has_changes=True), FakeGitForge()
    acts = _acts(factory, git=git, forge=forge)
    out = acts.open_pr({"run_id": run_id, "owner_id": "u1", "profile": "remote",
                        "branch": "agent/t1", "base": "main",
                        "title": "t", "body": "b"})
    assert out["pr_url"] == "https://github.com/fake/fake/pull/1"
    assert git.pushed and forge.opened
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.pr_url == "https://github.com/fake/fake/pull/1"


def test_open_pr_local_records_branch_only():
    factory = _factory()
    run_id = _seed_run(factory)
    git, forge = FakeGit(has_changes=True), FakeGitForge()
    acts = _acts(factory, git=git, forge=forge)
    out = acts.open_pr({"run_id": run_id, "owner_id": "u1", "profile": "local",
                        "branch": "agent/t1", "base": "main", "title": "t", "body": "b"})
    assert out["pr_url"] is None
    assert not git.pushed and not forge.opened
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        run = uow.runs.get(run_id)
    assert run.branch == "agent/t1"


def test_run_stage_populates_ctx_agent_from_team():
    from domain.models import AgentDefinition, Skill, Team

    factory = _factory()
    run_id = _seed_run(factory)

    # Seed a team, agent, and skill in the same owner scope
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        sk = uow.skills.create(Skill(owner_id="u1", name="pytest", source="git@x/s.git"))
        uow.agents.create(AgentDefinition(
            team_id=team.id, role="backend", name="Eng",
            model_alias="m", system_prompt="build",
            allowed_tools=["Read", "Edit"], skill_ids=[sk.id],
        ))

    captured = {}

    class _Spy:
        def run_stage(self, ctx):
            captured["ctx"] = ctx
            from domain.runtime import AgentEvent, StageResult
            yield AgentEvent(type="result", stage=ctx.stage, message="ok",
                             data=StageResult(outcome="ok").model_dump())

        def cancel(self, run_id):  # noqa: ARG002
            pass

    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    acts = RunActivities(factory, _Spy(), storage, FakeGit(), FakeGitForge())
    acts.run_stage({
        "run_id": run_id,
        "owner_id": "u1",
        "stage": "implement",
        "task_title": "T",
        "acceptance_criteria": [],
        "team_id": team.id,
    })

    ctx = captured["ctx"]
    assert ctx.agent is not None
    assert ctx.agent.system_prompt == "build"
    assert ctx.agent.allowed_tools == ["Read", "Edit"]
    assert ctx.agent.skills[0].source == "git@x/s.git"


def test_run_stage_injects_secret_env_without_leaking():
    import json
    import tempfile

    from cryptography.fernet import Fernet

    from adapters.secrets.cipher import FernetCipher
    from domain.models import AgentDefinition, Secret, Team
    from domain.runtime import AgentEvent, StageResult

    factory = _factory()
    run_id = _seed_run(factory)
    key = Fernet.generate_key().decode()
    cipher = FernetCipher(key)
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        sec = uow.secrets.create(Secret(owner_id="u1", name="GH_TOKEN",
                                        encrypted_value=cipher.encrypt("ghp_TOPSECRET")))
        uow.agents.create(AgentDefinition(team_id=team.id, role="backend", name="E",
                                          model_alias="m", secret_ids=[sec.id]))

    captured = {}

    class _Spy:
        def run_stage(self, ctx):
            captured["ctx"] = ctx
            yield AgentEvent(type="result", stage=ctx.stage, message="ok",
                             data=StageResult(outcome="ok").model_dump())

        def cancel(self, run_id):  # noqa: ARG002
            pass

    recorded = []
    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    acts = RunActivities(factory, _Spy(), storage, FakeGit(), FakeGitForge(), cipher=cipher)
    # capture every event the activity records
    orig = acts.record_event
    acts.record_event = lambda p: recorded.append(p) or orig(p)

    result = acts.run_stage({"run_id": run_id, "owner_id": "u1", "stage": "implement",
                             "task_title": "T", "acceptance_criteria": [], "team_id": team.id})

    # security invariant: plaintext injected in-process, never in output or events
    assert captured["ctx"].agent.secret_env == {"GH_TOKEN": "ghp_TOPSECRET"}
    assert "ghp_TOPSECRET" not in json.dumps(result)
    assert "ghp_TOPSECRET" not in json.dumps(recorded)


def test_run_stage_records_capability_audit_without_secret_values():
    import json
    import tempfile

    from cryptography.fernet import Fernet

    from adapters.secrets.cipher import FernetCipher
    from domain.models import AgentDefinition, Secret, Team
    from domain.runtime import AgentEvent, StageResult

    factory = _factory()
    run_id = _seed_run(factory)
    cipher = FernetCipher(Fernet.generate_key().decode())
    uow = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow.transaction():
        team = uow.teams.create(Team(owner_id="u1", name="T"))
        sec = uow.secrets.create(Secret(owner_id="u1", name="GH",
                                        encrypted_value=cipher.encrypt("ghp_SECRET")))
        uow.agents.create(AgentDefinition(
            team_id=team.id, role="backend", name="E",
            model_alias="engineer-model", allowed_tools=["Read", "Edit"],
            secret_ids=[sec.id],
        ))

    class _Spy:
        def run_stage(self, ctx):
            yield AgentEvent(type="result", stage=ctx.stage, message="ok",
                             data=StageResult(outcome="ok").model_dump())

        def cancel(self, run_id):  # noqa: ARG002
            pass

    storage = LocalStorageAdapter(base_dir=tempfile.mkdtemp())
    acts = RunActivities(factory, _Spy(), storage,
                         FakeGit(), FakeGitForge(), cipher=cipher)
    acts.run_stage({"run_id": run_id, "owner_id": "u1", "stage": "implement",
                    "task_title": "T", "acceptance_criteria": [], "team_id": team.id})

    uow2 = SqlUnitOfWork(factory, required_filters={"owner_id": "u1"})
    with uow2.transaction():
        events = uow2.audit_events.list(filters={"run_id": run_id}).results
    assert len(events) == 1
    detail = events[0].detail
    assert detail["tools"] == ["Read", "Edit"]
    assert detail["model_alias"] == "engineer-model"
    assert detail["secret_count"] == 1
    assert "ghp_SECRET" not in json.dumps(detail)  # no secret value in the audit
