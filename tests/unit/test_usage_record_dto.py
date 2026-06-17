from domain.agent.models import AgentRole
from domain.runs import Run, RunStage
from domain.usage import UsageRecord


def test_usage_record_has_hierarchy_and_token_fields():
    r = UsageRecord(
        owner_id="dev-user",
        run_id="run1",
        work_item_id="task1",
        project_id="proj1",
        stage=RunStage.IMPLEMENT,
        agent_role=AgentRole.BACKEND,
        model_id="claude-opus-4-8",
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.5,
    )
    assert r.id and len(r.id) == 32
    assert r.agent_role == AgentRole.BACKEND
    assert r.dedupe_key == "run1:implement:backend:claude-opus-4-8"


def test_usage_record_agent_role_optional():
    r = UsageRecord(owner_id="u", run_id="r", work_item_id="w", project_id="p",
                    stage=RunStage.PLAN, model_id="m")
    assert r.agent_role is None
    assert r.dedupe_key == "r:plan:none:m"


def test_run_defaults_token_counters_to_zero():
    run = Run(owner_id="u", task_id="t", team_id="tm")
    assert run.input_tokens == 0
    assert run.output_tokens == 0
    assert run.cache_read_tokens == 0
    assert run.cache_creation_tokens == 0
