import tempfile

from adapters.agent.runtime.fake import FakeAgentRuntime
from adapters.storage.local import LocalStorageAdapter
from domain.agent import AgentEvent, RunContext, StageResult, result_of
from domain.runs import RunStage


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


def test_fake_runtime_drives_orchestrator_decision_and_verdict(tmp_path):
    import json

    from adapters.agent.runtime.fake import FakeAgentRuntime
    from adapters.storage.local import LocalStorageAdapter
    from domain.agent import RunContext, result_of
    from domain.runs import RunStage

    storage = LocalStorageAdapter(base_dir=str(tmp_path))
    rt = FakeAgentRuntime(storage=storage)

    def _run(instructions, stage=RunStage.PLAN):
        ctx = RunContext(run_id="r1", stage=stage, task_title="T",
                         workspace_path=storage.local_path("runs/r1"), instructions=instructions)
        return result_of(list(rt.run_stage(ctx)))

    # Lead, wave 0 -> a continue decision dispatching the backend.
    _run("...Progress so far — wave 0... write to .orchestration/decision.json")
    decision = json.loads(storage.read_text("runs/r1/.orchestration/decision.json"))
    assert decision["intent"] == "continue"
    assert decision["dispatches"][0]["target_role"] == "backend"

    # Lead, later wave -> verify.
    _run("...Progress so far — wave 1... write to .orchestration/decision.json")
    decision2 = json.loads(storage.read_text("runs/r1/.orchestration/decision.json"))
    assert decision2["intent"] == "verify"

    # Monitor -> a complete verdict.
    _run("verify... write to .orchestration/verdict.json", stage=RunStage.VERIFY)
    assert json.loads(storage.read_text("runs/r1/.orchestration/verdict.json"))["complete"] is True
