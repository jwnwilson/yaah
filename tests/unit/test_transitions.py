import pytest

from domain.transitions import InvalidTransition, validate_transition
from domain.work_items import WorkItemStatus as S


@pytest.mark.parametrize(
    "src,dst",
    [
        (S.DRAFT, S.REFINING),
        (S.DRAFT, S.READY),
        (S.REFINING, S.READY),
        (S.READY, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.IN_REVIEW),
        (S.IN_PROGRESS, S.BLOCKED),
        (S.IN_PROGRESS, S.FAILED),
        (S.IN_REVIEW, S.APPROVED),
        (S.IN_REVIEW, S.IN_PROGRESS),
        (S.APPROVED, S.DONE),
        (S.BLOCKED, S.READY),
        (S.FAILED, S.READY),
    ],
)
def test_valid_transitions(src, dst):
    validate_transition(src, dst)  # must not raise


@pytest.mark.parametrize(
    "src,dst",
    [(S.DRAFT, S.DONE), (S.READY, S.DONE), (S.DONE, S.IN_PROGRESS), (S.DRAFT, S.IN_REVIEW)],
)
def test_invalid_transitions_raise(src, dst):
    with pytest.raises(InvalidTransition):
        validate_transition(src, dst)
