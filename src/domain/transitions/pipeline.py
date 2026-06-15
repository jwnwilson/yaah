from domain.models import AutonomyLevel, RunStage


def gates_for(autonomy: AutonomyLevel) -> set[RunStage]:
    if autonomy == AutonomyLevel.FULL_AUTO:
        return set()
    if autonomy == AutonomyLevel.GATED_MERGE:
        return {RunStage.PR}
    return {RunStage.PLAN, RunStage.PR}  # GATED_ALL
