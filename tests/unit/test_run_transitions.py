import pytest

from domain.models import RunStatus as R
from domain.run_transitions import validate_run_transition
from domain.transitions import InvalidTransition


def test_pending_can_be_cancelled():
    validate_run_transition(R.PENDING, R.CANCELLED)


def test_awaiting_approval_can_be_approved_to_done():
    validate_run_transition(R.AWAITING_APPROVAL, R.DONE)


def test_awaiting_approval_can_be_rejected_to_failed():
    validate_run_transition(R.AWAITING_APPROVAL, R.FAILED)


def test_done_is_terminal():
    with pytest.raises(InvalidTransition):
        validate_run_transition(R.DONE, R.CANCELLED)


def test_pending_cannot_jump_to_done():
    with pytest.raises(InvalidTransition):
        validate_run_transition(R.PENDING, R.DONE)
