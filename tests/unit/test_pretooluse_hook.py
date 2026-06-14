# tests/unit/test_pretooluse_hook.py
import io
import json

from adapters.agent.runtime import pretooluse_hook


def _run(monkeypatch, payload, allowed, audit_path):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setenv("YAAH_ALLOWED_TOOLS", json.dumps(allowed))
    monkeypatch.setenv("YAAH_AUDIT_PATH", audit_path)
    monkeypatch.setenv("YAAH_STAGE", "implement")
    return pretooluse_hook.main()


def test_allowed_tool_exit0_and_logged(monkeypatch, tmp_path):
    audit = str(tmp_path / "audit.jsonl")
    code = _run(monkeypatch, {"tool_name": "Read", "tool_input": {"x": 1}}, ["Read"], audit)
    assert code == 0
    line = json.loads(open(audit).read().strip())
    assert line["tool"] == "Read" and line["decision"] == "allow"


def test_denied_tool_exit2(monkeypatch, tmp_path):
    audit = str(tmp_path / "audit.jsonl")
    code = _run(monkeypatch, {"tool_name": "Bash", "tool_input": {"command": "echo SECRET"}},
               ["Read"], audit)
    assert code == 2
    body = open(audit).read()
    assert '"decision": "deny"' in body
    assert "SECRET" not in body   # tool input never recorded


def test_bad_stdin_fails_open(monkeypatch, tmp_path):
    audit = str(tmp_path / "audit.jsonl")
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    monkeypatch.setenv("YAAH_ALLOWED_TOOLS", "[]")
    monkeypatch.setenv("YAAH_AUDIT_PATH", audit)
    monkeypatch.setenv("YAAH_STAGE", "plan")
    # bad stdin -> tool="" -> not in allowlist -> deny (exit 2); must not crash
    assert pretooluse_hook.main() == 2
