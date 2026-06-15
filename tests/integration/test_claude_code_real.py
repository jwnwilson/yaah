import os
import shutil
import tempfile

import pytest

from adapters.agent.model.anthropic import AnthropicProvider
from adapters.agent.runtime.claude_code import ClaudeCodeRuntime
from domain.agent import RunContext, result_of
from domain.models import RunStage

_have = os.environ.get("ANTHROPIC_API_KEY") and shutil.which("claude")


@pytest.mark.skipif(not _have, reason="claude binary / ANTHROPIC_API_KEY not available")
def test_real_plan_stage_runs():
    ws = tempfile.mkdtemp()
    rt = ClaudeCodeRuntime(AnthropicProvider(model="claude-sonnet-4-6"))
    ctx = RunContext(run_id="r1", stage=RunStage.PLAN, task_title="Write a haiku to plan.md",
                    acceptance_criteria=[], workspace_path=ws)
    events = list(rt.run_stage(ctx))
    assert result_of(events).outcome in ("ok", "fail")
