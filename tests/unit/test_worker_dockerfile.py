from pathlib import Path


def test_worker_dockerfile_installs_claude_and_git():
    df = Path("infra/worker/Dockerfile").read_text()
    assert "claude-code" in df          # npm i -g @anthropic-ai/claude-code
    assert "git" in df


def test_compose_has_hardened_worker_service():
    compose = Path("docker-compose.yml").read_text()
    assert "worker:" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop" in compose
