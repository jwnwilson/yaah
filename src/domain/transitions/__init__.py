"""State-progression rules: the work-item and run status state machines plus the
run-stage pipeline (stage order, autonomy gates, verify-retry policy). Pure (no I/O).

`pipeline` is exposed as a submodule (``from domain.transitions import pipeline``);
the state-machine entry points are re-exported here so ``domain.transitions.InvalidTransition``
and ``domain.transitions.validate_transition`` keep resolving.
"""

from domain.transitions import pipeline
from domain.transitions.runs import validate_run_transition
from domain.transitions.work_items import InvalidTransition, validate_transition

__all__ = [
    "InvalidTransition",
    "pipeline",
    "validate_run_transition",
    "validate_transition",
]
