from domain.models import RunStage
from domain.runtime import AgentEvent, StageResult, RunContext


def test_runtime_dtos_construct():
    ctx = RunContext(run_id="r1", stage=RunStage.PLAN, task_title="T",
                     acceptance_criteria=["a"], workspace_path="/tmp/x")
    assert ctx.stage == RunStage.PLAN
    ev = AgentEvent(type="progress", stage=RunStage.PLAN, message="working")
    assert ev.type == "progress"
    res = StageResult(outcome="ok", cost_usd=0.5)
    assert res.outcome == "ok" and res.cost_usd == 0.5
