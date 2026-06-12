from domain.models import RunStage
from domain.runtime import AgentEvent, RunContext, StageResult
from adapters.runtime.fake import FakeAgentRuntime, result_of


def _ctx(stage):
    return RunContext(run_id="r1", stage=stage, task_title="T",
                      acceptance_criteria=[], workspace_path="/tmp/x")


def test_default_script_succeeds_every_stage():
    rt = FakeAgentRuntime()
    events = list(rt.run_stage(_ctx(RunStage.PLAN)))
    assert events[-1].type == "result"
    assert result_of(events).outcome == "ok"


def test_scripted_failure():
    script = {RunStage.VERIFY: [AgentEvent(type="result", stage=RunStage.VERIFY,
              data=StageResult(outcome="fail").model_dump())]}
    rt = FakeAgentRuntime(script=script)
    assert result_of(list(rt.run_stage(_ctx(RunStage.VERIFY)))).outcome == "fail"
