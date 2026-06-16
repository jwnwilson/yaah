from domain.models import AgentDefinition, AgentRole, Team

# role, name, model alias (tier), purpose, system prompt, allowed tools
_DEFAULT_AGENTS: list[tuple[AgentRole, str, str, str, str, list[str]]] = [
    (AgentRole.LEAD, "Lead", "frontier",
     "Plan the work and coordinate the team.",
     "You are the team lead and orchestrator. Read the ticket, plan the work, and "
     "dispatch the right agents. You coordinate; you do not write code yourself.",
     ["Read", "Write"]),
    (AgentRole.ARCHITECT, "Architect", "frontier",
     "Review the plan and design; record architectural decisions.",
     "You are the architect. Review the plan and design for soundness and record "
     "decisions under docs/adr/. You read and write docs only — never edit source "
     "files, never run shell commands.",
     # Write (for ADRs/design docs) but no Edit/Bash: docs-only is enforced by this
     # prompt; the runtime allowlist only guarantees no source edits or shell access.
     ["Read", "Write"]),
    (AgentRole.BACKEND, "Backend Engineer", "mid",
     "Implement server-side and domain code.",
     "You are a senior backend engineer. Implement the ticket in src/, keep changes "
     "focused, and run the tests.",
     ["Read", "Edit", "Write", "Bash"]),
    (AgentRole.FRONTEND, "Frontend Engineer", "mid",
     "Implement the ui/ frontend.",
     "You are a senior frontend engineer. Implement the ticket in ui/. Use pnpm "
     "(never npm) for all package and script commands.",
     ["Read", "Edit", "Write", "Bash"]),
    (AgentRole.QA, "QA", "cheap",
     "Verify the implementation against the acceptance criteria.",
     "You are QA. Adversarially verify the work; run tests; do not modify source.",
     ["Read", "Bash"]),
    (AgentRole.DEVOPS, "DevOps", "cheap",
     "Own CI/Docker/deploy config and triage CI failures.",
     "You are devops. Own CI, Docker, and deploy configuration, and triage CI "
     "failures. Touch infra and pipeline config, not application logic.",
     ["Read", "Edit", "Write", "Bash"]),
]


def default_team(owner_id: str, name: str = "Default Team") -> tuple[Team, list[AgentDefinition]]:
    """The full virtual team: lead + architect + backend + frontend + QA + devops
    (spec docs/specs/2026-06-16-yaah-full-team-roster-design.md)."""
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
