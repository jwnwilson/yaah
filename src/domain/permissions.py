"""Pure tool-permission policy for the PreToolUse interceptor. No I/O."""

from pydantic import BaseModel


class ToolDecision(BaseModel):
    allowed: bool
    reason: str = ""


def tool_decision(tool: str, allowed_tools: list[str]) -> ToolDecision:
    if tool in allowed_tools:
        return ToolDecision(allowed=True, reason="granted")
    return ToolDecision(allowed=False, reason="not in allowlist")
