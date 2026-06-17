import pytest
from pydantic import ValidationError

from domain.agent.models import AgentRole
from domain.projects import AutonomyLevel, Project
from domain.work_items import WorkItem, WorkItemKind, WorkItemStatus


def test_project_gets_id_and_defaults():
    p = Project(owner_id="dev-user", name="llm_api", repo_url="https://github.com/x/llm_api")
    assert len(p.id) == 32  # uuid hex
    assert p.autonomy == AutonomyLevel.GATED_ALL


def test_project_requires_repo_url_or_local_path():
    with pytest.raises(ValidationError):
        Project(owner_id="dev-user", name="nowhere")


def test_work_item_defaults_to_draft():
    w = WorkItem(owner_id="dev-user", project_id="p1", kind=WorkItemKind.EPIC, title="Auth")
    assert w.status == WorkItemStatus.DRAFT
    assert w.acceptance_criteria == []


def test_work_item_requires_owner():
    with pytest.raises(ValidationError):
        WorkItem(project_id="p1", kind=WorkItemKind.EPIC, title="x")


def test_epic_cannot_have_parent():
    with pytest.raises(ValidationError):
        WorkItem(
            owner_id="dev-user",
            project_id="p1",
            kind=WorkItemKind.EPIC,
            title="x",
            parent_id="other",
        )


def test_task_requires_parent():
    with pytest.raises(ValidationError):
        WorkItem(owner_id="dev-user", project_id="p1", kind=WorkItemKind.TASK, title="x")


def test_roles_enum_has_core_roles():
    assert {"lead", "architect", "backend", "frontend", "qa", "devops"} <= {
        r.value for r in AgentRole
    }


def test_capability_models_and_agent_grants():
    from domain.agent.models import AgentDefinition
    from domain.capabilities import McpServer, Secret, Skill

    s = Skill(owner_id="u", name="pytest", source="git@x/skills.git")
    m = McpServer(owner_id="u", name="fs", transport="stdio", command_or_url="npx mcp-fs",
                  tool_allowlist=["mcp__fs__read"])
    sec = Secret(owner_id="u", name="GH_TOKEN", description="github")
    assert s.id and m.tool_allowlist == ["mcp__fs__read"] and sec.name == "GH_TOKEN"

    a = AgentDefinition(team_id="t", role="lead", name="Lead", model_alias="lead-model",
                        purpose="run the show", system_prompt="You are the lead.",
                        allowed_tools=["Read", "Write"], skill_ids=[s.id],
                        mcp_server_ids=[m.id], secret_ids=[sec.id])
    assert a.purpose == "run the show" and a.skill_ids == [s.id]
    assert a.allowed_tools == ["Read", "Write"]


def test_audit_event_model():
    from domain.audit import AuditAction, AuditEvent
    from domain.runs import RunStage
    ev = AuditEvent(run_id="r1", owner_id="u", stage=RunStage.IMPLEMENT, actor="backend",
                    action=AuditAction.CAPABILITY_GRANTED,
                    detail={"tools": ["Read"], "model_alias": "engineer-model"})
    assert ev.id and ev.created_at
    assert ev.action == "capability_granted"
    assert ev.detail["tools"] == ["Read"]


def test_audit_action_tool_values():
    from domain.audit import AuditAction
    assert AuditAction.TOOL_ALLOWED == "tool_allowed"
    assert AuditAction.TOOL_DENIED == "tool_denied"


def test_run_stage_and_event_types_exist():
    from domain.runs import RunEvent, RunEventType, RunStage

    assert RunStage.PLAN == "plan"
    assert [s for s in RunStage] == [
        RunStage.PLAN, RunStage.PROVISION, RunStage.IMPLEMENT,
        RunStage.VERIFY, RunStage.PR, RunStage.LEARN,
    ]
    assert RunEventType.STAGE_STARTED == "stage_started"
    ev = RunEvent(run_id="r1", owner_id="dev-user", stage=RunStage.PLAN,
                  type=RunEventType.STAGE_STARTED, message="hi")
    assert ev.id and ev.created_at and ev.message == "hi"


def test_chat_models():
    from domain.refinement import ChatMessage, ChatRole, ChatSession
    s = ChatSession(owner_id="u", project_id="p")
    m = ChatMessage(owner_id="u", session_id=s.id, role=ChatRole.USER, content="hi")
    assert s.id and m.role == "user" and m.content == "hi" and s.epic_id is None


def test_orchestration_run_event_types_exist():
    from domain.runs import RunEventType

    assert RunEventType.AGENT_DISPATCHED == "agent_dispatched"
    assert RunEventType.AGENT_REPORTED == "agent_reported"
    assert RunEventType.MONITOR_STARTED == "monitor_started"
    assert RunEventType.MONITOR_VERDICT == "monitor_verdict"
    assert RunEventType.QUIESCENCE_REACHED == "quiescence_reached"


def test_role_memory_entry_defaults_and_role():
    from domain.agent.models import AgentRole
    from domain.memory import RoleMemoryEntry
    e = RoleMemoryEntry(owner_id="u1", role=AgentRole.BACKEND, content="prefer small PRs",
                        run_id="r1", project_id="p1")
    assert len(e.id) == 32 and e.role == AgentRole.BACKEND
    assert e.content == "prefer small PRs" and e.created_at is not None
    e2 = RoleMemoryEntry(owner_id="u1", role="qa", content="run the full suite")
    assert e2.role == AgentRole.QA and e2.run_id is None and e2.project_id is None
