import pytest

from domain.models import AgentRole
from domain.orchestration import (
    OrchestrationContractError,
    OrchestrationIntent,
    OrchestrationState,
    build_orchestrator_prompt,
    parse_decision,
    parse_verdict,
)


def test_prompt_mentions_ticket_roles_and_state():
    prompt = build_orchestrator_prompt(
        task_title="Add login",
        acceptance_criteria=["users can log in"],
        body="OAuth",
        state=OrchestrationState(waves=1, total_cost_usd=2.0),
        available_roles=[AgentRole.BACKEND, AgentRole.QA],
    )
    assert "Add login" in prompt
    assert "users can log in" in prompt
    assert "backend" in prompt and "qa" in prompt          # available roles listed
    assert "continue" in prompt and "verify" in prompt      # intents described
    assert "wave" in prompt.lower()                          # state digest present


def test_prompt_lists_every_intent():
    prompt = build_orchestrator_prompt(
        task_title="Add login",
        acceptance_criteria=["users can log in"],
        body="OAuth",
        state=OrchestrationState(),
        available_roles=[AgentRole.BACKEND],
    )
    for i in OrchestrationIntent:
        assert i.value in prompt


def test_parse_decision_validates_and_types():
    decision = parse_decision(
        {
            "intent": "continue",
            "dispatches": [{"target_role": "backend", "instructions": "do it"}],
            "assignee_role": "backend",
        }
    )
    assert decision.intent == OrchestrationIntent.CONTINUE
    assert decision.dispatches[0].target_role == AgentRole.BACKEND


def test_parse_decision_raises_contract_error_on_bad_payload():
    with pytest.raises(OrchestrationContractError):
        parse_decision({"intent": "continue"})  # continue with no dispatches/messages
    with pytest.raises(OrchestrationContractError):
        parse_decision({"intent": "nonsense"})  # not a valid intent


def test_parse_verdict_roundtrips():
    v = parse_verdict({"complete": False, "unmet": ["tests fail"]})
    assert v.complete is False and v.unmet == ["tests fail"]
    with pytest.raises(OrchestrationContractError):
        parse_verdict({"unmet": []})  # missing required 'complete'


def test_prompt_surfaces_unmet_acceptance_feedback():
    from domain.orchestration import MonitorVerdict

    state = OrchestrationState().record_verdict(
        MonitorVerdict(complete=False, unmet=["tests are missing"]))
    prompt = build_orchestrator_prompt(
        task_title="T", acceptance_criteria=["x"], body="", state=state,
        available_roles=[AgentRole.BACKEND])
    assert "NOT yet met" in prompt
    assert "tests are missing" in prompt


def test_prompt_includes_integration_conflict():
    s = OrchestrationState().record_integration({"branch": "agent/t__e1", "files": ["a.py"]})
    p = build_orchestrator_prompt(task_title="T", acceptance_criteria=[], body="",
                                  state=s, available_roles=[AgentRole.BACKEND])
    assert "a.py" in p and "conflict" in p.lower()
