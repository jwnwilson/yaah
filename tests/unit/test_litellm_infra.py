from pathlib import Path


def test_litellm_service_in_compose():
    compose = Path("docker-compose.yml").read_text()
    assert "litellm:" in compose
    assert "infra/litellm/config.yaml" in compose


def test_litellm_config_lists_aliases():
    cfg = Path("infra/litellm/config.yaml").read_text()
    for alias in ("lead-model", "engineer-model", "qa-model"):
        assert alias in cfg
