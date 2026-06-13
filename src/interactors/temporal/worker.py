import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.runtime.fake import FakeAgentRuntime
from adapters.storage.local import LocalStorageAdapter
from interactors.temporal.activities import RunActivities
from interactors.temporal.config import TemporalConfig
from interactors.temporal.workflows import RunWorkflow


def build_activities(database_url: str) -> list:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    storage = LocalStorageAdapter(base_dir="data/workspaces")
    acts = RunActivities(factory, FakeAgentRuntime(), storage)
    return [acts.persist_run_state, acts.record_event, acts.run_stage, acts.cleanup_workspace]


async def run_worker(config: TemporalConfig, database_url: str) -> None:  # pragma: no cover
    client = await Client.connect(config.address, namespace=config.namespace)
    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[RunWorkflow],
        activities=build_activities(database_url),
        activity_executor=ThreadPoolExecutor(max_workers=8),
    )
    await worker.run()


def main(config: TemporalConfig, database_url: str) -> None:  # pragma: no cover
    asyncio.run(run_worker(config, database_url))


def run() -> None:  # pragma: no cover
    from interactors.api.settings import Settings
    settings = Settings()
    main(TemporalConfig.from_settings(settings), settings.database_url)


if __name__ == "__main__":  # pragma: no cover
    run()
