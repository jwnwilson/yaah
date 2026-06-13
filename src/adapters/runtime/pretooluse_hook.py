"""Claude PreToolUse hook: decide + audit each tool call. Run as
`python -m adapters.runtime.pretooluse_hook`. Exit 0 = allow, 2 = deny. Fail-open."""

import json
import os
import sys
from datetime import datetime, timezone


def _append(path: str, record: dict) -> None:
    try:
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001 - audit is best-effort
        pass


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    tool = payload.get("tool_name") or payload.get("tool") or ""
    audit_path = os.environ.get("YAAH_AUDIT_PATH", "")
    stage = os.environ.get("YAAH_STAGE", "")
    try:
        allowed = json.loads(os.environ.get("YAAH_ALLOWED_TOOLS", "[]"))
    except json.JSONDecodeError:
        allowed = []

    try:
        from domain.permissions import tool_decision
        dec = tool_decision(tool, allowed)
        allowed_ok, reason = dec.allowed, dec.reason
    except Exception:  # noqa: BLE001 - fail-open: never brick the agent
        allowed_ok, reason = True, "auditor error"

    if audit_path:
        _append(audit_path, {
            "tool": tool, "decision": "allow" if allowed_ok else "deny",
            "reason": reason, "stage": stage,
            "ts": datetime.now(timezone.utc).isoformat(),
        })  # NOTE: tool inputs are intentionally NOT recorded
    if not allowed_ok:
        sys.stderr.write(f"yaah: tool '{tool}' denied: {reason}\n")
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
