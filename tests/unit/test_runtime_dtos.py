from domain.models import RunStage
from domain.runtime import AgentEvent, RunContext, StageResult
from domain.usage import TokenUsage


def test_runtime_dtos_construct():
    ctx = RunContext(run_id="r1", stage=RunStage.PLAN, task_title="T",
                     acceptance_criteria=["a"], workspace_path="/tmp/x")
    assert ctx.stage == RunStage.PLAN
    ev = AgentEvent(type="progress", stage=RunStage.PLAN, message="working")
    assert ev.type == "progress"
    res = StageResult(outcome="ok", cost_usd=0.5)
    assert res.outcome == "ok" and res.cost_usd == 0.5


def test_run_context_carries_optional_agent_manifest():
    from domain.capabilities import AgentManifest
    from domain.models import RunStage
    from domain.runtime import RunContext

    ctx = RunContext(run_id="r", stage=RunStage.IMPLEMENT, task_title="t",
                     workspace_path="/ws",
                     agent=AgentManifest(system_prompt="sp", allowed_tools=["Read"]))
    assert ctx.agent is not None and ctx.agent.system_prompt == "sp"

    bare = RunContext(run_id="r", stage=RunStage.PLAN, task_title="t", workspace_path="/ws")
    assert bare.agent is None


def test_stage_result_defaults_to_zero_usage():
    r = StageResult(outcome="ok")
    assert r.usage == TokenUsage()
    assert r.model_usage == {}


def test_stage_result_carries_per_model_usage():
    r = StageResult(
        outcome="ok",
        cost_usd=0.5,
        usage=TokenUsage(input_tokens=100, output_tokens=20, cost_usd=0.5),
        model_usage={
            "claude-opus-4-8": TokenUsage(input_tokens=100, output_tokens=20, cost_usd=0.5),
        },
    )
    assert r.usage.input_tokens == 100
    assert r.model_usage["claude-opus-4-8"].output_tokens == 20
