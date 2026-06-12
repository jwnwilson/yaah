import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from adapters.database.engine import make_engine, make_session_factory
from adapters.database.orm import Base
from adapters.runtime.fake import FakeAgentRuntime
from adapters.temporal.activities import RunActivities
from adapters.temporal.config import TemporalConfig
from adapters.temporal.workflow import RunWorkflow


def build_activities(database_url: str) -> list:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    acts = RunActivities(factory, FakeAgentRuntime())
    return [acts.persist_run_state, acts.record_event, acts.run_stage]


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
