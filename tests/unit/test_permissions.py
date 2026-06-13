from domain.permissions import tool_decision


def test_granted_tool_allowed():
    d = tool_decision("Read", ["Read", "Edit"])
    assert d.allowed and d.reason == "granted"


def test_ungranted_tool_denied():
    d = tool_decision("Bash", ["Read"])
    assert not d.allowed and "allowlist" in d.reason


def test_mcp_tool_exact_match():
    assert tool_decision("mcp__fs__read", ["mcp__fs__read"]).allowed
    assert not tool_decision("mcp__fs__write", ["mcp__fs__read"]).allowed
