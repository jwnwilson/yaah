from domain.models import AutonomyLevel, RunStage
from domain import pipeline


def test_stage_order():
    assert pipeline.STAGES == [
        RunStage.PLAN, RunStage.PROVISION, RunStage.IMPLEMENT,
        RunStage.VERIFY, RunStage.PR, RunStage.LEARN,
    ]


def test_gates_for_autonomy():
    assert pipeline.gates_for(AutonomyLevel.GATED_ALL) == {RunStage.PLAN, RunStage.PR}
    assert pipeline.gates_for(AutonomyLevel.GATED_MERGE) == {RunStage.PR}
    assert pipeline.gates_for(AutonomyLevel.FULL_AUTO) == set()


def test_verify_retry_policy():
    assert pipeline.VERIFY_MAX_LOOPS == 3
    assert pipeline.should_retry_verify(1) is True
    assert pipeline.should_retry_verify(3) is False
    assert pipeline.should_retry_verify(4) is False
