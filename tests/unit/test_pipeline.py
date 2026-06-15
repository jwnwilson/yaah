from domain.models import AutonomyLevel, RunStage
from domain.transitions import pipeline


def test_gates_for_autonomy():
    assert pipeline.gates_for(AutonomyLevel.GATED_ALL) == {RunStage.PLAN, RunStage.PR}
    assert pipeline.gates_for(AutonomyLevel.GATED_MERGE) == {RunStage.PR}
    assert pipeline.gates_for(AutonomyLevel.FULL_AUTO) == set()
