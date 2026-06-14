from domain.models import AutonomyLevel, RunStage

STAGES: list[RunStage] = [
    RunStage.PLAN,
    RunStage.PROVISION,
    RunStage.IMPLEMENT,
    RunStage.VERIFY,
    RunStage.PR,
    RunStage.LEARN,
]

VERIFY_MAX_LOOPS = 3


def gates_for(autonomy: AutonomyLevel) -> set[RunStage]:
    if autonomy == AutonomyLevel.FULL_AUTO:
        return set()
    if autonomy == AutonomyLevel.GATED_MERGE:
        return {RunStage.PR}
    return {RunStage.PLAN, RunStage.PR}  # GATED_ALL


def should_retry_verify(loops_used: int) -> bool:
    return loops_used < VERIFY_MAX_LOOPS
