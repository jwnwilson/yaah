import asyncio

from temporalio.client import Client

from interactors.temporal.config import TemporalConfig


class TemporalRunClient:
    """Sync facade over the async Temporal client for the sync FastAPI layer."""

    def __init__(self, config: TemporalConfig):
        self._config = config

    def _run(self, coro):
        return asyncio.run(coro)

    async def _client(self) -> Client:  # pragma: no cover
        return await Client.connect(self._config.address, namespace=self._config.namespace)

    def start_run_workflow(self, run_input: dict) -> None:  # pragma: no cover
        async def _go():
            client = await self._client()
            await client.start_workflow(
                "RunWorkflow",
                run_input,
                id=run_input["run_id"],
                task_queue=self._config.task_queue,
            )
        self._run(_go())

    def signal(self, run_id: str, name: str) -> None:  # pragma: no cover
        async def _go():
            client = await self._client()
            handle = client.get_workflow_handle(run_id)
            await handle.signal(name)
        self._run(_go())
