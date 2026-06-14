import tempfile

from adapters.agent.runtime.fake import FakeAgentRuntime, result_of
from adapters.storage.local import LocalStorageAdapter
from domain.models import RunStage
from domain.runtime import AgentEvent, RunContext, StageResult


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


def test_implement_writes_a_file_via_storage():
    base = tempfile.mkdtemp()
    storage = LocalStorageAdapter(base_dir=base)
    rt = FakeAgentRuntime(storage=storage)
    ctx = RunContext(run_id="r1", stage=RunStage.IMPLEMENT, task_title="T",
                     acceptance_criteria=[], workspace_path=storage.local_path("runs/r1"))
    list(rt.run_stage(ctx))
    assert storage.exists("runs/r1/IMPLEMENTED.md")
