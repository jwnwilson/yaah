from domain.agent.models import AgentRole, Team
from domain.agent.teams import default_team
from domain.runs import Run, RunStatus


def test_default_team_has_all_six_roles_in_order():
    team, agents = default_team(owner_id="dev-user")
    assert isinstance(team, Team)
    roles = [a.role for a in agents]
    assert roles == [
        AgentRole.LEAD,
        AgentRole.ARCHITECT,
        AgentRole.BACKEND,
        AgentRole.FRONTEND,
        AgentRole.QA,
        AgentRole.DEVOPS,
    ]
    assert all(a.team_id == team.id for a in agents)


def test_default_team_model_aliases_follow_tier_rubric():
    _, agents = default_team(owner_id="dev-user")
    by_role = {a.role: a.model_alias for a in agents}
    assert by_role[AgentRole.LEAD] == "frontier"
    assert by_role[AgentRole.ARCHITECT] == "frontier"
    assert by_role[AgentRole.BACKEND] == "mid"
    assert by_role[AgentRole.FRONTEND] == "mid"
    assert by_role[AgentRole.QA] == "cheap"
    assert by_role[AgentRole.DEVOPS] == "cheap"


def test_default_team_tool_grants_match_role_responsibilities():
    _, agents = default_team(owner_id="u")
    by_role = {a.role: a for a in agents}
    assert all(a.purpose and a.system_prompt for a in agents)
    # Architect is a review/design role: docs only, no source edits, no shell.
    assert "Edit" not in by_role[AgentRole.ARCHITECT].allowed_tools
    assert "Bash" not in by_role[AgentRole.ARCHITECT].allowed_tools
    # Engineers and devops edit and run commands.
    assert {"Edit", "Bash"} <= set(by_role[AgentRole.BACKEND].allowed_tools)
    assert {"Edit", "Bash"} <= set(by_role[AgentRole.FRONTEND].allowed_tools)
    assert "Edit" in by_role[AgentRole.DEVOPS].allowed_tools
    # QA is read-only.
    assert "Edit" not in by_role[AgentRole.QA].allowed_tools


def test_run_defaults():
    r = Run(owner_id="dev-user", task_id="t1", team_id="tm1")
    assert r.status == RunStatus.PENDING
    assert r.cost_usd == 0.0
    assert r.stage is None
