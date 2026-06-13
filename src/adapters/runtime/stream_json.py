"""Pure parser for Claude Code `--output-format stream-json` lines."""

import json
from typing import Iterable

from domain.models import RunStage
from domain.runtime import AgentEvent, StageResult


def _assistant_text(obj: dict) -> str:
    content = obj.get("message", {}).get("content", [])
    return " ".join(
        p.get("text", "") for p in content
        if isinstance(p, dict) and p.get("type") == "text"
    ).strip()


def parse(lines: Iterable[str], stage: RunStage) -> tuple[list[AgentEvent], StageResult]:
    events: list[AgentEvent] = []
    result = StageResult(outcome="ok")
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("type")
        if kind == "assistant":
            text = _assistant_text(obj)
            if text:
                events.append(AgentEvent(type="progress", stage=stage, message=text[:500]))
        elif kind == "result":
            outcome = "fail" if obj.get("is_error") else "ok"
            result = StageResult(
                outcome=outcome,
                cost_usd=float(obj.get("total_cost_usd") or 0.0),
                artifacts={"result": obj.get("result", "")},
            )
            events.append(AgentEvent(type="result", stage=stage, message="stage complete",
                                     data=result.model_dump()))
    return events, result
