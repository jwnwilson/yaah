from domain.agent import capabilities as cap
from domain.models import AgentDefinition, AgentRole, McpServer, RunStage, Skill


def _agent(role, **kw):
    return AgentDefinition(team_id="t", role=role, name=role, model_alias="m", **kw)


def test_role_for_stage():
    assert cap.role_for_stage(RunStage.PLAN) == AgentRole.LEAD
    assert cap.role_for_stage(RunStage.IMPLEMENT) == AgentRole.BACKEND
    assert cap.role_for_stage(RunStage.VERIFY) == AgentRole.QA
    assert cap.role_for_stage(RunStage.PR) is None  # non-agent stage


def test_select_agent_by_role_then_fallback():
    lead, eng = _agent(AgentRole.LEAD), _agent(AgentRole.BACKEND)
    assert cap.select_agent([lead, eng], RunStage.IMPLEMENT) is eng
    assert cap.select_agent([lead], RunStage.VERIFY) is lead       # fallback -> lead
    assert cap.select_agent([eng], RunStage.PLAN) is eng           # fallback -> first
    assert cap.select_agent([], RunStage.PLAN) is None


def test_assemble_manifest_from_grants():
    agent = _agent(AgentRole.BACKEND, system_prompt="you build",
                   allowed_tools=["Read", "Edit"], skill_ids=["s1"], mcp_server_ids=["m1"])
    skills = [Skill(owner_id="u", name="pytest", source="git@x/s.git")]
    mcps = [McpServer(owner_id="u", name="fs", transport="stdio",
                      command_or_url="npx mcp-fs", tool_allowlist=["mcp__fs__read"])]
    man = cap.assemble(agent, skills, mcps)
    assert man.system_prompt == "you build" and man.allowed_tools == ["Read", "Edit"]
    assert man.skills[0].name == "pytest" and man.skills[0].source == "git@x/s.git"
    assert man.mcp_servers[0].tool_allowlist == ["mcp__fs__read"]


def test_manifest_has_secret_env_default_empty():
    from domain.agent import AgentManifest
    assert AgentManifest().secret_env == {}
    m = AgentManifest(secret_env={"GH_TOKEN": "x"})
    assert m.secret_env["GH_TOKEN"] == "x"


def test_assemble_sets_model_alias():
    from domain.agent import assemble
    from domain.models import AgentDefinition, AgentRole
    agent = AgentDefinition(team_id="t", role=AgentRole.BACKEND, name="E",
                            model_alias="engineer-model")
    man = assemble(agent, [], [])
    assert man.model_alias == "engineer-model"
