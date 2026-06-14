from domain.models import WorkItemStatus as S


class InvalidTransition(Exception):
    pass


_ALLOWED: dict[S, set[S]] = {
    S.DRAFT: {S.REFINING, S.READY},
    S.REFINING: {S.READY, S.DRAFT},
    S.READY: {S.IN_PROGRESS, S.DRAFT},
    S.IN_PROGRESS: {S.IN_REVIEW, S.BLOCKED, S.FAILED},
    S.IN_REVIEW: {S.APPROVED, S.IN_PROGRESS},
    S.APPROVED: {S.DONE},
    S.BLOCKED: {S.READY},
    S.FAILED: {S.READY},
    S.DONE: set(),
}


def validate_transition(src: S, dst: S) -> None:
    if dst not in _ALLOWED[src]:
        raise InvalidTransition(f"cannot move work item from {src} to {dst}")
