from domain.models import AgentDefinition, AgentRole, Team

# role, name, model alias, purpose, system prompt, allowed tools
_DEFAULT_AGENTS: list[tuple[AgentRole, str, str, str, str, list[str]]] = [
    (AgentRole.LEAD, "Lead", "lead-model",
     "Plan the work and coordinate the team.",
     "You are the team lead. Read the ticket and produce a clear implementation plan.",
     ["Read", "Write"]),
    (AgentRole.BACKEND, "Engineer", "engineer-model",
     "Implement the ticket in the repository.",
     "You are a senior engineer. Implement the ticket and keep changes focused.",
     ["Read", "Edit", "Write", "Bash"]),
    (AgentRole.QA, "QA", "qa-model",
     "Verify the implementation against the acceptance criteria.",
     "You are QA. Adversarially verify the work; run tests; do not modify source.",
     ["Read", "Bash"]),
]


def default_team(owner_id: str, name: str = "Default Team") -> tuple[Team, list[AgentDefinition]]:
    """The Phase-A starter team: lead + engineer + QA (spec §10)."""
    team = Team(owner_id=owner_id, name=name)
    agents = [
        AgentDefinition(
            team_id=team.id,
            role=role,
            name=agent_name,
            model_alias=alias,
            purpose=purpose,
            system_prompt=system_prompt,
            allowed_tools=tools,
        )
        for role, agent_name, alias, purpose, system_prompt, tools in _DEFAULT_AGENTS
    ]
    return team, agents
