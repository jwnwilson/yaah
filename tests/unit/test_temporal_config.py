from interactors.api.settings import Settings
from adapters.temporal.config import TemporalConfig


def test_temporal_config_from_settings_defaults():
    cfg = TemporalConfig.from_settings(Settings(_env_file=None))
    assert cfg.address == "localhost:7233"
    assert cfg.namespace == "default"
    assert cfg.task_queue == "yaah-runs"
