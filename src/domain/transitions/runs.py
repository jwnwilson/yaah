from domain.models import RunStatus as R
from domain.transitions.work_items import InvalidTransition

_ALLOWED: dict[R, set[R]] = {
    R.PENDING: {R.RUNNING, R.CANCELLED},
    R.RUNNING: {R.AWAITING_APPROVAL, R.DONE, R.FAILED, R.BLOCKED, R.CANCELLED},
    R.AWAITING_APPROVAL: {R.DONE, R.FAILED, R.CANCELLED},
    R.BLOCKED: {R.RUNNING, R.CANCELLED},
    R.DONE: set(),
    R.FAILED: set(),
    R.CANCELLED: set(),
}


def validate_run_transition(src: R, dst: R) -> None:
    if dst not in _ALLOWED[src]:
        raise InvalidTransition(f"cannot move run from {src} to {dst}")
