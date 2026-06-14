"""Pure parser for Claude Code `--output-format stream-json` lines."""

import json
from typing import Iterable

from domain.agent import AgentEvent, StageResult
from domain.models import RunStage
from domain.usage import TokenUsage


def _assistant_text(obj: dict) -> str:
    content = obj.get("message", {}).get("content", [])
    return " ".join(
        p.get("text", "") for p in content
        if isinstance(p, dict) and p.get("type") == "text"
    ).strip()


_NOTIFY_TOOL = "yaah_notify"


def _notification_events(obj: dict, stage: RunStage) -> list[AgentEvent]:
    content = obj.get("message", {}).get("content", [])
    out: list[AgentEvent] = []
    for p in content:
        if not isinstance(p, dict) or p.get("type") != "tool_use" or p.get("name") != _NOTIFY_TOOL:
            continue
        data = p.get("input") or {}
        title = str(data.get("title") or "").strip()
        if not title:
            continue  # malformed: drop
        out.append(AgentEvent(type="notification", stage=stage, message=title[:200], data=data))
    return out


def _usage_from_top_level(obj: dict) -> TokenUsage:
    u = obj.get("usage") or {}
    return TokenUsage(
        input_tokens=int(u.get("input_tokens", 0)),
        output_tokens=int(u.get("output_tokens", 0)),
        cache_read_tokens=int(u.get("cache_read_input_tokens", 0)),
        cache_creation_tokens=int(u.get("cache_creation_input_tokens", 0)),
        cost_usd=float(obj.get("total_cost_usd") or 0.0),
    )


def _model_usage(obj: dict) -> dict[str, TokenUsage]:
    raw = obj.get("modelUsage") or {}
    out: dict[str, TokenUsage] = {}
    for model_id, m in raw.items():
        out[model_id] = TokenUsage(
            input_tokens=int(m.get("inputTokens", 0)),
            output_tokens=int(m.get("outputTokens", 0)),
            cache_read_tokens=int(m.get("cacheReadInputTokens", 0)),
            cache_creation_tokens=int(m.get("cacheCreationInputTokens", 0)),
            cost_usd=float(m.get("costUSD", 0.0)),
        )
    return out


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
            events.extend(_notification_events(obj, stage))
        elif kind == "result":
            outcome = "fail" if obj.get("is_error") else "ok"
            usage = _usage_from_top_level(obj)
            result = StageResult(
                outcome=outcome,
                cost_usd=usage.cost_usd,
                usage=usage,
                model_usage=_model_usage(obj),
                artifacts={"result": obj.get("result", "")},
            )
            events.append(AgentEvent(type="result", stage=stage, message="stage complete",
                                     data=result.model_dump()))
    return events, result
