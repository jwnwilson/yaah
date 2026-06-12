from adapters.temporal.config import TemporalConfig
from adapters.temporal.worker import main
from interactors.api.settings import Settings


def run() -> None:  # pragma: no cover
    settings = Settings()
    main(TemporalConfig.from_settings(settings), settings.database_url)


if __name__ == "__main__":  # pragma: no cover
    run()
