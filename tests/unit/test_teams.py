from domain.models import AgentRole, Run, RunStatus, Team
from domain.teams import default_team


def test_default_team_has_lead_engineer_qa():
    team, agents = default_team(owner_id="dev-user")
    assert isinstance(team, Team)
    roles = [a.role for a in agents]
    assert roles == [AgentRole.LEAD, AgentRole.BACKEND, AgentRole.QA]
    assert all(a.team_id == team.id for a in agents)


def test_default_team_model_aliases_follow_role_rubric():
    _, agents = default_team(owner_id="dev-user")
    by_role = {a.role: a.model_alias for a in agents}
    assert by_role[AgentRole.LEAD] == "lead-model"
    assert by_role[AgentRole.BACKEND] == "engineer-model"
    assert by_role[AgentRole.QA] == "qa-model"


def test_default_team_agents_have_purpose_and_tools():
    from domain.teams import default_team
    _team, agents = default_team(owner_id="u")
    by_role = {a.role: a for a in agents}
    assert all(a.purpose and a.system_prompt for a in agents)
    assert "Read" in by_role["lead"].allowed_tools
    assert "Edit" in by_role["backend"].allowed_tools
    assert "Edit" not in by_role["qa"].allowed_tools  # QA is read-only


def test_run_defaults():
    r = Run(owner_id="dev-user", task_id="t1", team_id="tm1")
    assert r.status == RunStatus.PENDING
    assert r.cost_usd == 0.0
    assert r.stage is None
