from domain.models import AgentDefinition, AgentRole, Team

_DEFAULT_AGENTS: list[tuple[AgentRole, str, str]] = [
    (AgentRole.LEAD, "Lead", "lead-model"),
    (AgentRole.BACKEND, "Engineer", "engineer-model"),
    (AgentRole.QA, "QA", "qa-model"),
]


def default_team(owner_id: str, name: str = "Default Team") -> tuple[Team, list[AgentDefinition]]:
    """The Phase-A starter team: lead + engineer + QA (spec §10)."""
    team = Team(owner_id=owner_id, name=name)
    agents = [
        AgentDefinition(team_id=team.id, role=role, name=agent_name, model_alias=alias)
        for role, agent_name, alias in _DEFAULT_AGENTS
    ]
    return team, agents
